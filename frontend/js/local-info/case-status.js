(function (global) {
  "use strict";

  var labels = {
    pending: "未處理", reported: "未處理", "待處理": "未處理", "已通報": "未處理", "未處理": "未處理",
    "in-progress": "處理中", "處理中": "處理中",
    resolved: "已結案", "已完成": "已結案", "已結案": "已結案"
  };

  global.caseStatusLabel = function (value, label) {
    function lookup(key) { return Object.prototype.hasOwnProperty.call(labels, key) ? labels[key] : ""; }
    return lookup(value) || lookup(label) || "狀態未提供";
  };
})(window);
