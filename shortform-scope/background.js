// 확장 아이콘을 누르면 사이드 패널이 열리게 한다.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});

// Alt+Shift+R: 사이드 패널을 열고 분석을 시작시킨다.
// sidePanel.open()은 단축키를 누른 '그 순간'에만 허용되므로 await 없이 먼저 호출한다.
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "analyze-current") return;
  // 패널이 아직 안 열렸으면, 패널이 뜨자마자 이 표시를 보고 분석을 시작한다.
  chrome.storage.session.set({ pendingAnalyze: Date.now() });
  chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
  // 패널이 이미 열려 있으면 바로 시작 신호를 받는다.
  chrome.runtime.sendMessage({ type: "start-analysis" }).catch(() => {});
});
