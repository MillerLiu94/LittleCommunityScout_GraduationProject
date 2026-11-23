(function (global) {
  "use strict";
  var form = document.getElementById("report-filters");
  var status = document.getElementById("filter-status");
  var category = document.getElementById("filter-category");
  var keyword = document.getElementById("filter-keyword");
  var feedback = document.getElementById("filter-feedback");
  var empty = document.getElementById("filter-empty");
  var isEvents = form.dataset.scope === "events";
  var list = document.getElementById(isEvents ? "events-list" : "reports-list");
  var count = document.getElementById(isEvents ? "event-count" : "report-count");
  var label = isEvents ? "社區事件" : "申報紀錄";
  var records = [];
  var changed = function () {};
  function active() { return Boolean(status.value || category.value || keyword.value.trim()); }
  function addOption(select, value) {
    if (!value || Array.from(select.options).some(function (option) { return option.value === value; })) return;
    select.add(new Option(value, value));
  }
  function refresh(finished) {
    var search = keyword.value.trim().toLocaleLowerCase();
    var visible = 0;
    records.forEach(function (item) {
      var record = item.record;
      var matches = (!status.value || record.status === status.value) &&
        (!category.value || record.category === category.value) &&
        (!search || [record.title, record.category, record.status, record.place, record.detail].join(" ").toLocaleLowerCase().includes(search));
      item.card.hidden = !matches;
      if (matches) visible += 1;
    });
    empty.hidden = !active() || !finished || visible > 0;
    document.getElementById("empty-state").hidden = active() || records.length > 0 || !finished;
    count.textContent = "目前顯示 " + visible + " 筆" + label;
  }
  form.addEventListener("submit", function (event) { event.preventDefault(); });
  form.addEventListener("input", function () { feedback.textContent = ""; changed(); });
  document.getElementById("copy-filter").addEventListener("click", function () {
    var text = (isEvents ? "社區事件" : "我的申報") + "篩選條件：案件狀態：" + (status.value || "全部") + "；事件類別：" + (category.value || "全部") + "；關鍵字：" + (keyword.value.trim() || "無");
    if (!navigator.clipboard || !navigator.clipboard.writeText) { feedback.textContent = "無法複製，請確認瀏覽器剪貼簿權限。"; return; }
    navigator.clipboard.writeText(text).then(function () { feedback.textContent = "已複製篩選條件，可貼到 AI 小助理。"; }).catch(function () { feedback.textContent = "複製失敗，請確認瀏覽器剪貼簿權限。"; });
  });
  global.ReportFilters = {
    active: active,
    refresh: refresh,
    onChange: function (callback) { changed = callback; },
    add: function (record, card) { records.push({ record: record, card: card }); addOption(category, record.category); list.appendChild(card); }
  };
})(window);
