import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

import "lib/status.js" as Status

// AI usage & balance pill. Reads ~/.cache/aium/status.json (written by the
// `aium` CLI poll) and shows the top metric plus a worst-provider health dot.
// Left/right click opens the detail panel; hover shows a tooltip.
BarWidget {
  id: root
  moduleName: "jonykalavera.aium"

  // ---- settings (inline shell.json layout entry, same names as the GNOME schema) ----
  readonly property string topMetric: setting("top-metric", "spend_month")
  readonly property real warnThreshold: Number(setting("balance-warn", 10))
  readonly property real criticalThreshold: Number(setting("balance-critical", 1))
  readonly property bool showZeroBalance: setting("show-zero-balance", false) === true

  // ---- status data (single source: this widget; the panel reads via hostWidget) ----
  property var status: null
  readonly property bool hasData: status !== null
  readonly property var totals: hasData ? (status.totals ?? {}) : null
  readonly property string pillText: hasData ? Status.panelMetric(totals, topMetric) : "n/a"
  readonly property string tooltip: Status.tooltipText(status)

  // Worst health across shown providers: -1 no dot, 0 good, 1 warn, 2 critical.
  readonly property int dotLevel: {
    if (!hasData) return -1
    var providers = status.providers ?? []
    var worst = -1
    for (var i = 0; i < providers.length; i++) {
      var provider = providers[i]
      if (!root.showZeroBalance && !Status.isRelevant(provider)) continue
      var level = Status.healthLevel(provider, root.warnThreshold, root.criticalThreshold)
      if (level !== null && level > worst) worst = level
    }
    return worst
  }

  function levelColor(level) {
    var rgb = Status.LEVEL_COLORS[level]
    return Qt.rgba(rgb[0], rgb[1], rgb[2], 1)
  }

  function providerColor(provider) {
    var level = Status.healthLevel(provider, root.warnThreshold, root.criticalThreshold)
    return level === null ? "transparent" : root.levelColor(level)
  }

  // Pill dot: worst severity across shown providers.
  readonly property color pillDotColor: dotLevel < 0 ? "transparent" : root.levelColor(dotLevel)

  // Providers shown in the panel (mirror of the GNOME menu filter).
  readonly property var relevantProviders: {
    if (!hasData) return []
    var list = status.providers ?? []
    var out = []
    for (var i = 0; i < list.length; i++) {
      var provider = list[i]
      if (root.showZeroBalance || Status.isRelevant(provider)) out.push(provider)
    }
    return out
  }

  // ---- status.json watch ----
  readonly property string statusPath: {
    var base = Quickshell.env("AIUM_CACHE_HOME")
    if (base) return base + "/aium/status.json"
    base = Quickshell.env("XDG_CACHE_HOME") || (Quickshell.env("HOME") + "/.cache")
    return base + "/aium/status.json"
  }

  function parseStatus(jsonText) {
    if (!jsonText) return null
    try {
      return JSON.parse(jsonText)
    } catch (e) {
      return null
    }
  }

  FileView {
    id: statusFile
    path: root.statusPath
    watchChanges: true
    printErrors: false
    onLoaded: root.status = root.parseStatus(text())
    onLoadFailed: root.status = null
  }

  // FileView can't observe a file that doesn't exist yet (the first `aium
  // poll` may not have run), so watch the parent directory and reload on
  // any change — same pattern the bar uses for its toggle flags.
  FileView {
    id: statusDir
    path: root.statusPath.slice(0, root.statusPath.lastIndexOf("/"))
    watchChanges: true
    printErrors: false
    onFileChanged: statusFile.reload()
  }

  // ---- panel wiring (weather-style: the bar tracks this widget, the panel is loaded) ----
  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = pillRow
    if ("hostWidget" in target) target.hostWidget = root
  }

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  function togglePanel() {
    if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle()
  }

  // Shape contract for shell.summon/hide/toggle routing (Bar.findPanelWidget
  // requires open/close/opened on the bar-widget root).
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item && panelLoader.item.open) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item && panelLoader.item.close) panelLoader.item.close()
  }

  // Forwarded so this widget can stand in for the panel as the bar's popout
  // identity (open-panel dot + switchPanelFrom lookups).
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  // ---- the pill ----
  visible: true
  implicitWidth: pillRow.implicitWidth + Style.space(16)
  implicitHeight: barSize

  Row {
    id: pillRow
    anchors.centerIn: parent
    spacing: Style.space(6)

    Rectangle {
      id: dot
      visible: root.dotLevel >= 0
      width: 7
      height: 7
      radius: 3.5
      anchors.verticalCenter: parent.verticalCenter
      color: root.pillDotColor
    }

    Text {
      id: label
      textFormat: Text.PlainText
      visible: !root.bar || !root.bar.vertical
      text: root.pillText
      color: root.bar ? root.bar.barForeground : Color.foreground
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.body
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  MouseArea {
    id: hover
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    onClicked: function(mouse) {
      root.togglePanel()
    }
    onEntered: if (root.bar) root.bar.showTooltip(root, root.tooltip)
    onExited: if (root.bar) root.bar.hideTooltip(root)
  }
}
