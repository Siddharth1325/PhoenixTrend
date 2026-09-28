/* PhoenixTrend premium interaction layer. Visual-only behavior lives here;
   broker, market, risk and execution logic remains in the FastAPI backend. */
(() => {
  "use strict";
  const state = { observer: null, raf: 0 };
  const qs = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => [...r.querySelectorAll(s)];
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));

  function pointerGlow(el, ev) {
    const r = el.getBoundingClientRect();
    const x = clamp(ev.clientX-r.left,0,r.width);
    const y = clamp(ev.clientY-r.top,0,r.height);
    el.style.setProperty('--mx', `${x}px`);
    el.style.setProperty('--my', `${y}px`);
  }

  function attachGlass() {
    qsa('.pt-panel,.metric-card,.scanner,.strategy-card,.symbol-strip button').forEach(el => {
      if (el.dataset.glassReady) return;
      el.dataset.glassReady='1';
      el.addEventListener('pointermove', e => pointerGlow(el,e), {passive:true});
      el.addEventListener('pointerleave', () => {el.style.removeProperty('--mx');el.style.removeProperty('--my')},{passive:true});
    });
  }

  function attachBrokerGlass() {
    qsa('.top-broker-glass').forEach(el => {
      if (el.dataset.brokerGlassReady) return;
      el.dataset.brokerGlassReady = '1';
      el.addEventListener('pointermove', e => {
        const r = el.getBoundingClientRect();
        el.style.setProperty('--broker-x', `${e.clientX-r.left}px`);
        el.style.setProperty('--broker-y', `${e.clientY-r.top}px`);
      }, {passive:true});
      el.addEventListener('pointerleave', () => { el.style.removeProperty('--broker-x'); el.style.removeProperty('--broker-y'); }, {passive:true});
    });
  }

  function attachTabs() {
    qsa('.tabbar,.ai-modebar,.order-types,.buy-sell').forEach(group => {
      if(group.dataset.tabsReady) return;
      group.dataset.tabsReady='1';
      group.addEventListener('click', e => {
        const b=e.target.closest('button'); if(!b) return;
        qsa('button',group).forEach(x=>x.classList.remove('active')); b.classList.add('active');
      });
    });
  }

  function attachSearchShortcut() {
    if(document.body.dataset.searchReady) return;
    document.body.dataset.searchReady='1';
    document.addEventListener('keydown', e => {
      if(e.key==='/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName||'')) {
        e.preventDefault(); qs('.global-search input')?.focus();
      }
      if(e.key==='Escape' && /INPUT|TEXTAREA/.test(document.activeElement?.tagName||'')) document.activeElement.blur();
    });
  }

  function animateNumbers() {
    qsa('.metric-value').forEach(el => {
      if(el.dataset.numberReady) return; el.dataset.numberReady='1';
      el.animate([{opacity:.35,transform:'translateY(3px)'},{opacity:1,transform:'none'}],{duration:320,easing:'ease-out'});
    });
  }

  function attachParallax() {
    const banner=qs('.shell-banner'); if(!banner || banner.dataset.parallaxReady) return;
    banner.dataset.parallaxReady='1';
    banner.addEventListener('pointermove',e=>{
      const r=banner.getBoundingClientRect(); const x=((e.clientX-r.left)/r.width-.5)*5;
      banner.style.transform=`translate3d(${x}px,0,0)`;
    },{passive:true});
    banner.addEventListener('pointerleave',()=>banner.style.transform='',{passive:true});
  }

  function observePanels() {
    state.observer?.disconnect();
    state.observer=new IntersectionObserver(entries=>entries.forEach(entry=>{
      if(entry.isIntersecting){entry.target.classList.add('is-visible');state.observer.unobserve(entry.target)}
    }),{threshold:.06});
    qsa('.pt-panel,.metric-card,.scanner').forEach(x=>state.observer.observe(x));
  }

  function init() {
    cancelAnimationFrame(state.raf);
    state.raf=requestAnimationFrame(()=>{attachGlass();attachBrokerGlass();attachTabs();attachSearchShortcut();animateNumbers();attachParallax();observePanels()});
  }
  new MutationObserver(init).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('DOMContentLoaded',init);
  window.PhoenixTrend={init};
})();
