from __future__ import annotations

import asyncio
import hashlib
import hmac
import math
import secrets
import time
import uuid

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArenaBet:
    id: str
    player_id: str
    player_name: str
    amount: int
    round_id: str
    placed_at: float

    cashed_out: bool = False
    cashout_multiplier: float | None = None
    payout: int = 0


@dataclass
class ArenaRound:
    id: str
    sequence: int

    server_seed: str
    commitment: str

    crash_multiplier: float

    phase: str = "countdown"

    countdown_started_at: float = field(
        default_factory=time.time
    )

    started_at: float | None = None
    crashed_at: float | None = None

    revealed_seed: str | None = None

    bets: dict[str, ArenaBet] = field(
        default_factory=dict
    )


class ArenaService:
    """
    Server-authoritative Phoenix Flight simulation.

    Phoenix Coins are virtual-only simulation currency.

    Round result is generated and committed before betting opens.

    Player actions cannot modify the predetermined flight result.
    """

    COUNTDOWN_SECONDS = 5.0

    RESULT_SECONDS = 3.0

    GROWTH_RATE = 0.115

    MAX_MULTIPLIER = 100.0

    STARTING_BALANCE = 10_000

    MIN_BET = 100

    MAX_BET = 2_500

    ENGINE_TICK_SECONDS = 0.025

    HISTORY_LIMIT = 24

    BET_FEED_LIMIT = 50


    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        self._runner: asyncio.Task | None = None

        self._sequence = 0

        self._round: ArenaRound | None = None

        self._history: deque[dict[str, Any]] = deque(
            maxlen=self.HISTORY_LIMIT
        )

        self._balances: dict[str, int] = {}

        self._names: dict[str, str] = {}

        self._stats: dict[str, Any] = {
            "total_rounds": 0,
            "highest": 1.0,
            "longest_seconds": 0.0,
        }


    # ======================================================================
    # SERVICE LIFECYCLE
    # ======================================================================

    async def start(self) -> None:
        if (
            self._runner is not None
            and not self._runner.done()
        ):
            return

        async with self._lock:
            if self._round is None:
                self._round = self._new_round()

        self._runner = asyncio.create_task(
            self._run(),
            name="phoenix-arena-round-engine",
        )


    async def stop(self) -> None:
        runner = self._runner

        self._runner = None

        if runner is None:
            return

        runner.cancel()

        try:
            await runner
        except asyncio.CancelledError:
            pass


    # ======================================================================
    # ROUND GENERATION
    # ======================================================================

    def _new_round(self) -> ArenaRound:
        self._sequence += 1

        seed = secrets.token_hex(32)

        commitment = hashlib.sha256(
            seed.encode("utf-8")
        ).hexdigest()

        crash_multiplier = self._crash_from_seed(
            seed,
            self._sequence,
        )

        return ArenaRound(
            id=(
                f"PFA-{self._sequence:08d}-"
                f"{uuid.uuid4().hex[:6]}"
            ),
            sequence=self._sequence,
            server_seed=seed,
            commitment=commitment,
            crash_multiplier=crash_multiplier,
        )


    @staticmethod
    def _crash_from_seed(
        seed: str,
        sequence: int,
    ) -> float:
        digest = hmac.new(
            seed.encode("utf-8"),
            str(sequence).encode("utf-8"),
            hashlib.sha256,
        ).digest()

        value = (
            int.from_bytes(
                digest[:8],
                "big",
            )
            / float(2**64)
        )

        value = min(
            max(
                value,
                0.000000001,
            ),
            0.999999999,
        )

        multiplier = (
            0.99
            / (1.0 - value)
        )

        return round(
            min(
                max(
                    multiplier,
                    1.01,
                ),
                100.0,
            ),
            2,
        )


    # ======================================================================
    # MULTIPLIER
    # ======================================================================

    @classmethod
    def multiplier_for_elapsed(
        cls,
        elapsed: float,
    ) -> float:
        elapsed = max(
            0.0,
            float(elapsed),
        )

        multiplier = math.exp(
            elapsed
            * cls.GROWTH_RATE
        )

        return min(
            max(
                multiplier,
                1.0,
            ),
            cls.MAX_MULTIPLIER,
        )


    @classmethod
    def seconds_to_multiplier(
        cls,
        multiplier: float,
    ) -> float:
        multiplier = min(
            max(
                float(multiplier),
                1.0,
            ),
            cls.MAX_MULTIPLIER,
        )

        return (
            math.log(multiplier)
            / cls.GROWTH_RATE
        )


    # ======================================================================
    # ROUND ENGINE
    # ======================================================================

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(
                    self.ENGINE_TICK_SECONDS
                )

                async with self._lock:
                    self._advance_round_unlocked(
                        time.time()
                    )

        except asyncio.CancelledError:
            raise


    def _advance_round_unlocked(
        self,
        now: float,
    ) -> None:
        round_state = self._round

        if round_state is None:
            self._round = self._new_round()
            return

        if round_state.phase == "countdown":
            elapsed = (
                now
                - round_state.countdown_started_at
            )

            if (
                elapsed
                >= self.COUNTDOWN_SECONDS
            ):
                round_state.phase = "flying"

                round_state.started_at = now

            return

        if round_state.phase == "flying":
            if round_state.started_at is None:
                round_state.started_at = now

            elapsed = max(
                0.0,
                now
                - round_state.started_at,
            )

            multiplier = (
                self.multiplier_for_elapsed(
                    elapsed
                )
            )

            if (
                multiplier
                >= round_state.crash_multiplier
            ):
                self._finish_round_unlocked(
                    round_state,
                    now,
                )

            return

        if round_state.phase == "crashed":
            crashed_at = (
                round_state.crashed_at
                or now
            )

            if (
                now - crashed_at
                >= self.RESULT_SECONDS
            ):
                self._round = (
                    self._new_round()
                )


    def _finish_round_unlocked(
        self,
        round_state: ArenaRound,
        now: float,
    ) -> None:
        if round_state.phase == "crashed":
            return

        round_state.phase = "crashed"

        round_state.crashed_at = now

        round_state.revealed_seed = (
            round_state.server_seed
        )

        started_at = (
            round_state.started_at
            or now
        )

        flight_seconds = max(
            0.0,
            now - started_at,
        )

        self._stats["total_rounds"] = (
            int(
                self._stats.get(
                    "total_rounds",
                    0,
                )
            )
            + 1
        )

        self._stats["highest"] = max(
            float(
                self._stats.get(
                    "highest",
                    1.0,
                )
            ),
            round_state.crash_multiplier,
        )

        self._stats["longest_seconds"] = max(
            float(
                self._stats.get(
                    "longest_seconds",
                    0.0,
                )
            ),
            flight_seconds,
        )

        self._history.appendleft(
            {
                "round_id": round_state.id,
                "multiplier": (
                    round_state.crash_multiplier
                ),
                "commitment": (
                    round_state.commitment
                ),
                "server_seed": (
                    round_state.server_seed
                ),
                "sequence": (
                    round_state.sequence
                ),
                "flight_seconds": round(
                    flight_seconds,
                    3,
                ),
            }
        )


    # ======================================================================
    # PLAYER
    # ======================================================================

    def _ensure_player(
        self,
        player_id: str,
        player_name: str,
    ) -> None:
        player_id = str(
            player_id or ""
        ).strip()

        if not player_id:
            raise ValueError(
                "Player ID is required."
            )

        cleaned_name = str(
            player_name or ""
        ).strip()

        if not cleaned_name:
            cleaned_name = (
                "Phoenix Trader"
            )

        cleaned_name = cleaned_name[:32]

        if (
            player_id
            not in self._balances
        ):
            self._balances[player_id] = (
                self.STARTING_BALANCE
            )

        self._names[player_id] = (
            cleaned_name
        )


    def _find_player_bet_unlocked(
        self,
        round_state: ArenaRound,
        player_id: str,
    ) -> ArenaBet | None:
        for bet in round_state.bets.values():
            if bet.player_id == player_id:
                return bet

        return None


    # ======================================================================
    # SNAPSHOT HELPERS
    # ======================================================================

    def _serialize_bet(
        self,
        bet: ArenaBet,
    ) -> dict[str, Any]:
        return {
            "id": bet.id,
            "player_id": bet.player_id,
            "player_name": bet.player_name,
            "amount": bet.amount,
            "round_id": bet.round_id,
            "placed_at": bet.placed_at,
            "cashed_out": bet.cashed_out,
            "cashout_multiplier": (
                bet.cashout_multiplier
            ),
            "payout": bet.payout,
        }


    def _serialize_own_bet(
        self,
        bet: ArenaBet | None,
    ) -> dict[str, Any] | None:
        if bet is None:
            return None

        return {
            "id": bet.id,
            "amount": bet.amount,
            "round_id": bet.round_id,
            "placed_at": bet.placed_at,
            "cashed_out": bet.cashed_out,
            "cashout_multiplier": (
                bet.cashout_multiplier
            ),
            "payout": bet.payout,
        }


    # ======================================================================
    # SNAPSHOT
    # ======================================================================

    def _snapshot_unlocked(
        self,
        player_id: str,
        player_name: str,
    ) -> dict[str, Any]:
        self._ensure_player(
            player_id,
            player_name,
        )

        now = time.time()

        self._advance_round_unlocked(
            now
        )

        round_state = self._round

        if round_state is None:
            return {
                "ready": False,
                "server_time": now,
            }

        elapsed = 0.0

        if round_state.started_at is not None:
            elapsed = max(
                0.0,
                now
                - round_state.started_at,
            )

        if round_state.phase == "countdown":
            current_multiplier = 1.0

        elif round_state.phase == "flying":
            current_multiplier = (
                self.multiplier_for_elapsed(
                    elapsed
                )
            )

            current_multiplier = min(
                current_multiplier,
                round_state.crash_multiplier,
            )

        else:
            current_multiplier = (
                round_state.crash_multiplier
            )

        if round_state.phase == "countdown":
            countdown = max(
                0.0,
                self.COUNTDOWN_SECONDS
                - (
                    now
                    - round_state.countdown_started_at
                ),
            )
        else:
            countdown = 0.0

        own_bet = (
            self._find_player_bet_unlocked(
                round_state,
                player_id,
            )
        )

        all_bets = list(
            round_state.bets.values()
        )

        visible_bets = all_bets[
            -self.BET_FEED_LIMIT:
        ]

        serialized_bets = [
            self._serialize_bet(bet)
            for bet in visible_bets
        ]

        crash_multiplier = None
        revealed_seed = None

        if (
            round_state.phase
            == "crashed"
        ):
            crash_multiplier = (
                round_state.crash_multiplier
            )

            revealed_seed = (
                round_state.revealed_seed
            )

        return {
            "ready": True,

            "server_time": now,

            "round": {
                "id": round_state.id,

                "sequence": (
                    round_state.sequence
                ),

                "phase": (
                    round_state.phase
                ),

                "commitment": (
                    round_state.commitment
                ),

                "current_multiplier": round(
                    current_multiplier,
                    4,
                ),

                "countdown": round(
                    countdown,
                    3,
                ),

                "countdown_started_at": (
                    round_state.countdown_started_at
                ),

                "started_at": (
                    round_state.started_at
                ),

                "crashed_at": (
                    round_state.crashed_at
                ),

                "crash_multiplier": (
                    crash_multiplier
                ),

                "server_seed": (
                    revealed_seed
                ),
            },

            "player": {
                "id": player_id,

                "name": (
                    self._names[player_id]
                ),

                "balance": (
                    self._balances[player_id]
                ),
            },

            "my_bet": (
                self._serialize_own_bet(
                    own_bet
                )
            ),

            "bets": serialized_bets,

            "history": list(
                self._history
            ),

            "stats": {
                "total_rounds": int(
                    self._stats.get(
                        "total_rounds",
                        0,
                    )
                ),

                "highest": round(
                    float(
                        self._stats.get(
                            "highest",
                            1.0,
                        )
                    ),
                    2,
                ),

                "longest_seconds": round(
                    float(
                        self._stats.get(
                            "longest_seconds",
                            0.0,
                        )
                    ),
                    2,
                ),
            },

            "rules": {
                "min_bet": self.MIN_BET,

                "max_bet": self.MAX_BET,

                "starting_balance": (
                    self.STARTING_BALANCE
                ),

                "max_multiplier": (
                    self.MAX_MULTIPLIER
                ),

                "countdown_seconds": (
                    self.COUNTDOWN_SECONDS
                ),

                "virtual_only": True,
            },
        }


    # ======================================================================
    # PUBLIC SNAPSHOT
    # ======================================================================

    async def snapshot(
        self,
        player_id: str,
        player_name: str,
    ) -> dict[str, Any]:
        async with self._lock:
            return self._snapshot_unlocked(
                player_id,
                player_name,
            )


    # ======================================================================
    # PLACE BET
    # ======================================================================

    async def place_bet(
        self,
        player_id: str,
        player_name: str,
        amount: int,
    ) -> dict[str, Any]:
        async with self._lock:
            self._ensure_player(
                player_id,
                player_name,
            )

            now = time.time()

            self._advance_round_unlocked(
                now
            )

            round_state = self._round

            if (
                round_state is None
                or round_state.phase
                != "countdown"
            ):
                raise ValueError(
                    "Bets are accepted only during the countdown."
                )

            try:
                amount = int(amount)
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    "Bet amount must be a whole number."
                ) from exc

            if (
                amount < self.MIN_BET
                or amount > self.MAX_BET
            ):
                raise ValueError(
                    f"Bet must be between "
                    f"{self.MIN_BET} and "
                    f"{self.MAX_BET} "
                    f"Phoenix Coins."
                )

            existing_bet = (
                self._find_player_bet_unlocked(
                    round_state,
                    player_id,
                )
            )

            if existing_bet is not None:
                raise ValueError(
                    "You already placed a bet for this round."
                )

            balance = (
                self._balances[player_id]
            )

            if balance < amount:
                raise ValueError(
                    "Not enough Phoenix Coins."
                )

            bet = ArenaBet(
                id=uuid.uuid4().hex,

                player_id=player_id,

                player_name=(
                    self._names[player_id]
                ),

                amount=amount,

                round_id=(
                    round_state.id
                ),

                placed_at=now,
            )

            self._balances[player_id] = (
                balance - amount
            )

            round_state.bets[
                bet.id
            ] = bet

            return (
                self._snapshot_unlocked(
                    player_id,
                    player_name,
                )
            )


    # ======================================================================
    # CANCEL BET
    # ======================================================================

    async def cancel_bet(
        self,
        player_id: str,
        player_name: str,
    ) -> dict[str, Any]:
        async with self._lock:
            self._ensure_player(
                player_id,
                player_name,
            )

            self._advance_round_unlocked(
                time.time()
            )

            round_state = self._round

            if (
                round_state is None
                or round_state.phase
                != "countdown"
            ):
                raise ValueError(
                    "The bet can no longer be cancelled."
                )

            own_bet = (
                self._find_player_bet_unlocked(
                    round_state,
                    player_id,
                )
            )

            if own_bet is None:
                raise ValueError(
                    "No active bet for this round."
                )

            self._balances[player_id] += (
                own_bet.amount
            )

            round_state.bets.pop(
                own_bet.id,
                None,
            )

            return (
                self._snapshot_unlocked(
                    player_id,
                    player_name,
                )
            )


    # ======================================================================
    # CASH OUT
    # ======================================================================

    async def cash_out(
        self,
        player_id: str,
        player_name: str,
    ) -> dict[str, Any]:
        async with self._lock:
            self._ensure_player(
                player_id,
                player_name,
            )

            now = time.time()

            self._advance_round_unlocked(
                now
            )

            round_state = self._round

            if (
                round_state is None
                or round_state.phase
                != "flying"
                or round_state.started_at
                is None
            ):
                raise ValueError(
                    "There is no active flight to cash out from."
                )

            own_bet = (
                self._find_player_bet_unlocked(
                    round_state,
                    player_id,
                )
            )

            if own_bet is None:
                raise ValueError(
                    "No active bet for this round."
                )

            if own_bet.cashed_out:
                return (
                    self._snapshot_unlocked(
                        player_id,
                        player_name,
                    )
                )

            elapsed = max(
                0.0,
                now
                - round_state.started_at,
            )

            current_multiplier = (
                self.multiplier_for_elapsed(
                    elapsed
                )
            )

            if (
                current_multiplier
                >= round_state.crash_multiplier
            ):
                self._finish_round_unlocked(
                    round_state,
                    now,
                )

                raise ValueError(
                    "The Phoenix already flew away."
                )

            settled_multiplier = max(
                1.0,
                math.floor(
                    current_multiplier
                    * 100
                )
                / 100,
            )

            settled_multiplier = min(
                settled_multiplier,
                round_state.crash_multiplier,
                self.MAX_MULTIPLIER,
            )

            payout = int(
                math.floor(
                    own_bet.amount
                    * settled_multiplier
                )
            )

            own_bet.cashed_out = True

            own_bet.cashout_multiplier = (
                settled_multiplier
            )

            own_bet.payout = payout

            self._balances[player_id] += (
                payout
            )

            return (
                self._snapshot_unlocked(
                    player_id,
                    player_name,
                )
            )


arena_service = ArenaService()