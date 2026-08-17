(function(){
"use strict";
var token = localStorage.getItem("vmon_token") || "";
var currentPlatform = "";
var query = "";

function api(method, path, body, retried) {
  var opts = { method: method, headers: {} };
  if (token) opts.headers["X-Access-Token"] = token;
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  return fetch(path, opts).then(function (r) {
    return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, data: j }; });
  }).then(function (res) {
    if (res.status === 401 && !retried) {
      var t = window.prompt("请输入访问口令（设置在 设置-网页访问 中）");
      if (t) { token = t; localStorage.setItem("vmon_token", t); return api(method, path, body, true); }
    }
    return res;
  });
}

function toast(msg) {
  var el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(function () { el.classList.add("hidden"); }, 2600);
}

function esc(s) {
  var d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function fmtTime(ts) {
  if (!ts) return "";
  var d = new Date(ts * 1000);
  var p = function (n) { return (n < 10 ? "0" : "") + n; };
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}

var PLATFORM = { xueqiu: "雪球", weibo: "微博" };
var KIND = { post: "发布了新帖", repost: "转发了动态", comment: "发表了评论", article: "发布了文章" };

function kvRow(k, v) {
  return '<div class="kv-row"><span class="k">' + esc(k) + '</span><span>' + v + '</span></div>';
}

/* ---------- 动态 ---------- */
function renderFeed(items) {
  var list = document.getElementById("feed-list");
  var empty = document.getElementById("feed-empty");
  list.innerHTML = "";
  if (!items.length) { empty.classList.remove("hidden"); return; }
  empty.classList.add("hidden");
  items.forEach(function (it) {
    var card = document.createElement("div");
    card.className = "item-card platform-" + it.platform;
    var kind = KIND[it.kind] || "有新动态";
    var html = '<div class="item-head">' +
      '<span class="badge ' + it.platform + '">' + PLATFORM[it.platform] + '</span>' +
      '<span class="item-name">' + esc(it.user_name) + '</span>' +
      '<span class="item-kind">' + esc(kind) + '</span>' +
      '<span class="item-time">' + esc(fmtTime(it.ts)) + '</span>' +
      '</div>';
    if (it.text) html += '<div class="item-text">' + esc(it.text) + '</div>';
    html += '<a class="item-link" href="' + esc(it.url) + '" target="_blank" rel="noopener">查看原文 ↗</a>';
    card.innerHTML = html;
    list.appendChild(card);
  });
}

function loadFeed() {
  var url = "/api/items?limit=100";
  if (currentPlatform) url += "&platform=" + encodeURIComponent(currentPlatform);
  if (query) url += "&q=" + encodeURIComponent(query);
  api("GET", url).then(function (res) {
    if (res.status === 200) renderFeed(res.data.items);
    else if (res.status !== 401) toast(res.data.error || "加载失败");
  }).catch(function () { toast("网络错误"); });
}

/* ---------- 管理 ---------- */
function loadInfluencers() {
  api("GET", "/api/influencers").then(function (res) {
    if (res.status !== 200) return;
    var list = document.getElementById("inf-list");
    list.innerHTML = "";
    res.data.influencers.forEach(function (inf) {
      var card = document.createElement("div");
      card.className = "inf-card";
      var meta = inf.resolved ? ("ID: " + esc(inf.user_id) + (inf.last_seen ? " · 最近 " + esc(inf.last_seen) : "")) : "未解析 ID，请编辑";
      var st = inf.enabled ? '<span class="ok">监控中</span>' : '<span class="no">已停用</span>';
      card.innerHTML =
        '<div class="grow">' +
          '<div class="inf-name">' + esc(inf.name) + ' <span class="badge ' + inf.platform + '">' + PLATFORM[inf.platform] + '</span></div>' +
          '<div class="inf-meta">' + meta + " · " + st + '</div>' +
        '</div>' +
        '<label class="switch"><input type="checkbox" ' + (inf.enabled ? "checked" : "") + ' data-id="' + esc(inf.id) + '"><span class="slider"></span></label>' +
        '<button class="btn btn-danger" data-del="' + esc(inf.id) + '">删除</button>';
      list.appendChild(card);
    });
    list.querySelectorAll("input[type=checkbox]").forEach(function (cb) {
      cb.addEventListener("change", function () { toggleInf(cb.dataset.id, cb.checked); });
    });
    list.querySelectorAll("[data-del]").forEach(function (btn) {
      btn.addEventListener("click", function () { delInf(btn.dataset.del); });
    });
  });
}

function toggleInf(id, enabled) {
  api("PUT", "/api/influencers/" + encodeURIComponent(id), { enabled: enabled }).then(function (res) {
    toast(res.status === 200 ? (enabled ? "已启用" : "已停用") : (res.data.error || "操作失败"));
    loadInfluencers(); loadStatus();
  });
}

function delInf(id) {
  if (!window.confirm("确定删除这位大V吗？")) return;
  api("DELETE", "/api/influencers/" + encodeURIComponent(id)).then(function (res) {
    toast(res.status === 200 ? "已删除" : (res.data.error || "删除失败"));
    loadInfluencers(); loadStatus();
  });
}

function openModal() {
  document.getElementById("modal").classList.remove("hidden");
  document.getElementById("inf-name").value = "";
  document.getElementById("inf-user-id").value = "";
}
function closeModal() { document.getElementById("modal").classList.add("hidden"); }

function saveInfluencer() {
  var name = document.getElementById("inf-name").value.trim();
  var platform = document.getElementById("inf-platform").value;
  var ref = document.getElementById("inf-user-id").value.trim();
  if (!name) { toast("请填写大V名称"); return; }
  if (!ref) { toast("请填写数字 ID 或主页链接"); return; }
  api("POST", "/api/influencers", { name: name, platform: platform, user_id: ref }).then(function (res) {
    if (res.status === 200) { toast("已添加"); closeModal(); loadInfluencers(); loadStatus(); }
    else toast(res.data.error || "添加失败");
  });
}

/* ---------- 设置 ---------- */
function loadStatus() {
  api("GET", "/api/status").then(function (res) {
    if (res.status !== 200) return;
    var s = res.data;
    var sec = s.secrets || {};
    var chName = sec.push_channel === "wecom" ? "企业微信" : (sec.push_channel === "pushplus" ? "PushPlus" : "未配置");
    var wecomOk = sec.wecom_corpid && sec.wecom_secret && sec.wecom_agent_id;
    var rows = [
      ["推送渠道", chName],
      ["PushPlus Token", sec.pushplus_token ? '<span class="ok">已配置</span>' : '<span class="no">未配置</span>'],
      ["企业微信（可选）", wecomOk ? '<span class="ok">已配置</span>' : '<span class="no">未配置</span>'],
      ["雪球 Cookie", sec.xueqiu_cookie ? '<span class="ok">已配置</span>' : '<span class="no">未配置</span>'],
      ["微博 Cookie", sec.weibo_cookie ? '<span class="ok">已配置</span>' : '<span class="no">未配置</span>'],
    ];
    document.getElementById("secrets-status").innerHTML = rows.map(function (r) { return kvRow(r[0], r[1]); }).join("");

    var pi = s.config.poll_interval_minutes || {};
    var mrows = [
      ["雪球轮询间隔", (pi.xueqiu || "?") + " 分钟"],
      ["微博轮询间隔", (pi.weibo || "?") + " 分钟"],
      ["首次回填", s.config.initial_backfill_hours + " 小时"],
      ["历史条目", s.storage_count + " 条"],
      ["Git 仓库", s.git.repo ? '<span class="ok">是</span>' : '<span class="no">否（仅本地）</span>'],
      ["Git 远程", s.git.remote ? '<span class="ok">已配置</span>' : '<span class="no">未配置</span>'],
    ];
    document.getElementById("monitor-config").innerHTML = mrows.map(function (r) { return kvRow(r[0], r[1]); }).join("");

    document.getElementById("allow-lan").checked = !!s.config.web.allow_lan;

    var lr = s.last_run || {};
    var lrows = [["最后运行", esc(lr.finished_at || "从未运行")]];
    var sm = lr.summary || {};
    if (lr.finished_at) {
      lrows.push(["本次抓取", (sm.fetched || 0) + " 条"]);
      lrows.push(["本次新增", (sm.new || 0) + " 条"]);
      lrows.push(["本次推送", (sm.pushed || 0) + " 条"]);
      if (sm.errors && sm.errors.length) lrows.push(["错误", '<span class="no">' + esc(sm.errors.join("；")) + '</span>']);
      if (sm.degraded && sm.degraded.length) lrows.push(["降级", esc(sm.degraded.join("、")) + "（评论监控不可用）"]);
      if (sm.cookie_invalid && sm.cookie_invalid.length) lrows.push(["Cookie 失效", '<span class="no">' + esc(sm.cookie_invalid.join("、")) + "，请刷新 Cookie</span>"]);
    }
    document.getElementById("last-run").innerHTML = lrows.map(function (r) { return kvRow(r[0], r[1]); }).join("");
  });
}

function loadLogs() {
  api("GET", "/api/logs").then(function (res) {
    if (res.status === 200) document.getElementById("logs").textContent = (res.data.logs || []).join("");
  });
}

function doRefresh() {
  api("POST", "/api/refresh").then(function (res) {
    if (res.status === 200) { toast(res.data.message || "刷新中…"); }
    else toast(res.data.error || "刷新失败");
    setTimeout(loadFeed, 4000);
    setTimeout(loadStatus, 6000);
    setTimeout(loadLogs, 8000);
  }).catch(function () { toast("刷新失败"); });
}

function testPush() {
  api("POST", "/api/test_push").then(function (res) {
    toast(res.data.message || res.data.error || "发送失败");
  });
}

function saveSettings() {
  var allowLan = document.getElementById("allow-lan").checked;
  var t = document.getElementById("access-token").value.trim();
  api("POST", "/api/settings", { allow_lan: allowLan, access_token: t }).then(function (res) {
    toast(res.status === 200 ? (res.data.message || "已保存") : (res.data.error || "保存失败"));
    if (res.status === 200) { token = t; localStorage.setItem("vmon_token", t); loadStatus(); }
  });
}

/* ---------- 事件绑定 ---------- */
function bind() {
  var tabs = document.querySelectorAll(".tab");
  tabs.forEach(function (tb) {
    tb.addEventListener("click", function () {
      tabs.forEach(function (x) { x.classList.remove("active"); });
      tb.classList.add("active");
      document.querySelectorAll(".view").forEach(function (v) { v.classList.remove("active"); });
      document.getElementById("view-" + tb.dataset.tab).classList.add("active");
    });
  });
  document.querySelectorAll(".chip").forEach(function (ch) {
    ch.addEventListener("click", function () {
      document.querySelectorAll(".chip").forEach(function (x) { x.classList.remove("active"); });
      ch.classList.add("active");
      currentPlatform = ch.dataset.platform;
      loadFeed();
    });
  });
  var search = document.getElementById("search");
  search.addEventListener("input", function () { query = search.value.trim(); loadFeed(); });
  document.getElementById("btn-refresh").addEventListener("click", doRefresh);
  document.getElementById("btn-add").addEventListener("click", openModal);
  document.getElementById("btn-modal-cancel").addEventListener("click", closeModal);
  document.getElementById("btn-modal-save").addEventListener("click", saveInfluencer);
  document.getElementById("btn-test-push").addEventListener("click", testPush);
  document.getElementById("btn-save-settings").addEventListener("click", saveSettings);
  document.getElementById("modal").addEventListener("click", function (e) { if (e.target.id === "modal") closeModal(); });
}

bind();
loadFeed();
loadInfluencers();
loadStatus();
loadLogs();
setInterval(loadFeed, 30000);
})();
