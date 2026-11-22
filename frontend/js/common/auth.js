(function (global) {
  "use strict";

  var scriptUrl = document.currentScript ? document.currentScript.src : location.href;
  var appRoot = new URL("../../", scriptUrl);
  var callbackResult = "";
  var currentUser = null;

  function clearReauthentication() {
    try { sessionStorage.removeItem("communityAuthReauthenticate"); } catch (_) {}
  }

  function processCallback() {
    var params = new URLSearchParams(location.search);
    var result = params.get("login");
    if (result === "success" || result === "failed" || params.has("reason")) {
      callbackResult = result === "failed" || params.has("reason") ? "failed" : "success";
      if (callbackResult === "success") clearReauthentication();
      params.delete("login");
      params.delete("role");
      params.delete("reason");
      history.replaceState({}, "", location.pathname + (params.toString() ? "?" + params : "") + location.hash);
    }
  }

  function returnAfterLogin() {
    var home = new URL("index.html", appRoot).href;
    var target = "";
    try { target = sessionStorage.getItem("communityAuthReturnTo") || ""; sessionStorage.removeItem("communityAuthReturnTo"); } catch (_) {}
    if (target.indexOf(appRoot.pathname) !== 0) target = home;
    global.location.replace(target);
  }

  function initialize(page) {
    processCallback();
    return global.CommunityApi.getCurrentUser().then(function (user) {
      currentUser = user;
      var reauthenticate = new URLSearchParams(location.search).get("reauth") === "1";
      try { reauthenticate = reauthenticate || sessionStorage.getItem("communityAuthReauthenticate") === "1"; } catch (_) {}
      if (page === "login" && reauthenticate && !callbackResult) callbackResult = "reauth";
      if (page === "login" && callbackResult !== "failed" && callbackResult !== "reauth") returnAfterLogin();
      return user;
    }).catch(function (error) {
      currentUser = null;
      if ((page === "home" || page === "protected") && error.status === 401) global.CommunityApi.redirectToLogin(true);
      if (page === "login" && error.status === 401) clearReauthentication();
      if (page === "login" && callbackResult === "success" && error.status === 401) callbackResult = "invalid";
      if (page === "login" && error.status && error.status !== 401) throw error;
      return null;
    });
  }

  global.CommunityAuth = {
    initialize: initialize,
    read: function () { return currentUser; },
    clearReauthentication: clearReauthentication,
    callbackResult: function () { return callbackResult; },
  };
})(window);
