import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui

import "lib/status.js" as Status

// Detail popup for the aium bar pill: totals summary plus one row per
// provider (health dot, name, detail line). Data comes from the host
// BarWidget (which owns the status.json FileView); settings come from the
// injected shell.json layout entry.
Panel {
  id: root
  moduleName: "jonykalavera.aium"
  ipcTarget: "jonykalavera.aium"

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property var status: hostWidget ? hostWidget.status : null
  readonly property bool hasData: status !== null
  readonly property var totals: hasData ? (status.totals ?? {}) : null
  readonly property string currency: totals ? (totals.currency ?? "USD") : "USD"

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool showZeroBalance: setting("show-zero-balance", false) === true

  readonly property var providers: hasData ? (hostWidget?.relevantProviders ?? []) : []
  readonly property string updatedText: {
    if (!hasData || !status.generated_at) return ""
    var at = new Date(status.generated_at)
    return isNaN(at.getTime()) ? "" : "updated " + Qt.formatDateTime(at, "ddd d MMM, HH:mm")
  }

  function money(value) {
    return Status.moneyShort(value, root.currency)
  }

  function providerDotColor(provider) {
    return hostWidget && hostWidget.providerColor
      ? hostWidget.providerColor(provider)
      : "transparent"
  }

  PopupCard {
    id: popup
    anchorItem: root.anchorItem
    bar: root.bar
    owner: root.barIdentity
    open: root.opened
    contentWidth: popup.fittedContentWidth(Style.space(340))
    contentHeight: popup.fittedContentHeight(column.implicitHeight)

    Flickable {
      anchors.fill: parent
      contentWidth: width
      contentHeight: column.implicitHeight
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      flickableDirection: Flickable.VerticalFlick
      interactive: contentHeight > height
      ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(10)

        // ---------- Header ----------
        Column {
          width: parent.width
          spacing: 0

          Text {
            width: parent.width
            textFormat: Text.PlainText
            text: "AI Usage"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            elide: Text.ElideRight
          }

          Text {
            width: parent.width
            visible: root.updatedText !== ""
            textFormat: Text.PlainText
            text: root.updatedText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
          }
        }

        // ---------- Totals ----------
        Row {
          width: parent.width
          spacing: Style.space(12)

          Repeater {
            model: [
              { label: "This month", value: root.hasData ? root.money(root.totals.spend_this_month) : "—" },
              { label: "Today", value: root.hasData ? root.money(root.totals.spend_today) : "—" },
              { label: "Balance", value: root.hasData ? root.money(root.totals.balance) : "—" },
            ]

            Column {
              width: (parent.width - Style.space(12) * 2) / 3
              spacing: 2

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: modelData.label
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: modelData.value
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                elide: Text.ElideRight
              }
            }
          }
        }

        PanelSeparator {
          width: parent.width
          foreground: root.foreground
        }

        // ---------- Providers ----------
        Text {
          visible: root.providers.length === 0
          width: parent.width
          textFormat: Text.PlainText
          text: root.hasData ? "No relevant providers." : "No data — run `aium poll` first."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Repeater {
          model: root.providers

          Row {
            required property var modelData

            width: column.width
            spacing: Style.space(8)

            Rectangle {
              visible: modelData !== undefined
              width: 8
              height: 8
              radius: 4
              anchors.verticalCenter: nameText.verticalCenter
              color: root.providerDotColor(modelData)
            }

            Column {
              width: parent.width - 8 - Style.space(8)
              spacing: 1

              Text {
                id: nameText
                width: parent.width
                textFormat: Text.PlainText
                text: modelData.name ?? ""
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: Status.providerDetail(modelData)
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }
          }
        }
      }
    }
  }
}
