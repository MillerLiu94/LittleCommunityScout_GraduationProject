(function () {
  "use strict";
  var toggle = document.getElementById("assistant-toggle");
  var panel = document.getElementById("assistant-panel");
  var close = document.getElementById("assistant-close");
  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) document.getElementById("prompt").focus();
    else toggle.focus();
  }
  toggle.addEventListener("click", function () { setOpen(panel.hidden); });
  close.addEventListener("click", function () { setOpen(false); });
  panel.addEventListener("keydown", function (event) { if (event.key === "Escape") setOpen(false); });
})();
