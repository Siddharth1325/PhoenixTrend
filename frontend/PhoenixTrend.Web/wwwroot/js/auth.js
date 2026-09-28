window.phoenixAuth = {
    get: function (key) { return window.localStorage.getItem(key); },
    set: function (key, value) { window.localStorage.setItem(key, value); },
    remove: function (key) { window.localStorage.removeItem(key); }
};
