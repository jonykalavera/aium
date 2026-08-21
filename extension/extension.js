import Cairo from 'gi://cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {money, moneyShort} from './lib/format.js';
import {isRelevant, providerDetail, severityColor, tooltipText} from './lib/status.js';

const STATUS_PATH = GLib.build_filenamev([
    GLib.get_user_cache_dir(), 'aium', 'status.json',
]);

function findAiumBinary() {
    const candidate = GLib.build_filenamev([
        GLib.get_home_dir(), '.local', 'bin', 'aium',
    ]);
    if (GLib.file_test(candidate, GLib.FileTest.IS_EXECUTABLE))
        return candidate;
    return 'aium';
}

class PanelTooltip {
    constructor(actor) {
        this._actor = actor;
        this._label = new St.Label({
            style_class: 'aium-tooltip',
            text: '',
        });
        Main.uiGroup.add_child(this._label);
        this._label.hide();

        this._enterId = actor.connect('enter-event', () => this._onEnter());
        this._leaveId = actor.connect('leave-event', () => this._onLeave());
    }

    set text(value) {
        this._label.text = value;
    }

    _onEnter() {
        if (!this._label.text)
            return;
        const [x, y] = this._actor.get_transformed_position();
        const [w, h] = this._actor.get_transformed_size();
        this._label.opacity = 0;
        this._label.show();
        const labelX = Math.round(x + w / 2 - this._label.width / 2);
        const labelY = Math.round(y + h + 6);
        this._label.set_position(labelX, labelY);
        this._label.opacity = 255;
    }

    _onLeave() {
        this._label.hide();
    }

    destroy() {
        if (this._enterId) {
            this._actor.disconnect(this._enterId);
            this._enterId = 0;
        }
        if (this._leaveId) {
            this._actor.disconnect(this._leaveId);
            this._leaveId = 0;
        }
        this._label?.destroy();
        this._label = null;
    }
}

const Sparkline = GObject.registerClass(
class Sparkline extends St.DrawingArea {
    constructor(values, color, max = null) {
        super({ style_class: 'aium-sparkline' });
        this._values = values ?? [];
        this._color = color ?? [0.4, 0.6, 1.0];
        this._max = max;
        this.connect('repaint', () => this._draw());
    }

    vfunc_get_preferred_width() {
        return [40, 96];
    }

    vfunc_get_preferred_height() {
        return [14, 14];
    }

    _draw() {
        const [width, height] = this.get_surface_size();
        const cr = this.get_context();
        cr.setOperator(Cairo.Operator.CLEAR);
        cr.paint();
        cr.setOperator(Cairo.Operator.SOURCE);

        const values = this._values;
        if (values.length < 2)
            return;

        const max = this._max ?? Math.max(...values, 0.01);
        const n = values.length;
        const stepX = width / (n - 1);
        const [r, g, b] = this._color;
        const y = i =>
            height - Math.min(1, Math.max(0, values[i] / max)) * (height - 1);

        cr.moveTo(0, height);
        for (let i = 0; i < n; i++)
            cr.lineTo(i * stepX, y(i));
        cr.lineTo(width, height);
        cr.closePath();
        cr.setSourceRGBA(r, g, b, 0.25);
        cr.fill();

        cr.moveTo(0, y(0));
        for (let i = 1; i < n; i++)
            cr.lineTo(i * stepX, y(i));
        cr.setSourceRGBA(r, g, b, 1.0);
        cr.setLineWidth(1.5);
        cr.stroke();
    }
});

export default class AiumExtension extends Extension {
    enable() {
        this._settings = this.getSettings();

        this._button = new PanelMenu.Button(0.0, this.metadata.name, false);
        this._icon = this._createIcon();
        this._label = new St.Label({
            text: '…',
            style_class: 'aium-label',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._content = new St.BoxLayout({ style_class: 'aium-panel-content' });
        this._content.add_child(this._icon);
        this._content.add_child(this._label);
        this._button.add_child(this._content);

        Main.panel.addToStatusArea('aium', this._button);

        this._tooltip = new PanelTooltip(this._button);

        this._refresh();
        this._installTimer();
        this._settings.connect(
            'changed::refresh-interval-seconds',
            () => this._installTimer(),
        );
        this._settings.connect('changed::show-label', () => this._refresh());
        this._settings.connect('changed::summary-mode', () => this._refresh());
    }

    _createIcon() {
        // Self-contained: prefer the SVG bundled with the extension so the
        // extension works from a plain zip; fall back to the icon theme.
        const path = `${this.path}/icons/aium-robot-symbolic.svg`;
        if (GLib.file_test(path, GLib.FileTest.EXISTS)) {
            return new St.Icon({
                gicon: Gio.icon_new_for_string(path),
                style_class: 'system-status-icon',
                icon_size: 16,
            });
        }
        return new St.Icon({
            icon_name: 'aium-robot-symbolic',
            style_class: 'system-status-icon',
            icon_size: 16,
        });
    }

    _installTimer() {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }
        const interval = this._settings.get_int('refresh-interval-seconds');
        this._timeoutId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, interval, () => {
                this._refresh();
                return GLib.SOURCE_CONTINUE;
            },
        );
    }

    _readStatus() {
        try {
            const [ok, contents] = GLib.file_get_contents(STATUS_PATH);
            if (!ok)
                return null;
            return JSON.parse(new TextDecoder().decode(contents));
        } catch (e) {
            return null;
        }
    }

    _refresh() {
        const status = this._readStatus();
        this._updateLabel(status);
        this._updateTooltip(status);
        this._rebuildMenu(status);
    }

    _updateLabel(status) {
        this._label.visible = this._settings.get_boolean('show-label');
        if (!status) {
            this._label.text = 'n/a';
            return;
        }
        const totals = status.totals ?? {};
        const mode = this._settings.get_string('summary-mode');
        const spend = moneyShort(totals.spend_this_month, totals.currency);
        const balance = moneyShort(totals.balance, totals.currency);
        if (mode === 'spend')
            this._label.text = spend;
        else if (mode === 'balance')
            this._label.text = balance;
        else
            this._label.text = `${spend}\n${balance}`;
    }

    _updateTooltip(status) {
        this._tooltip.text = tooltipText(status);
    }

    _rebuildMenu(status) {
        this._button.menu.removeAll();

        const summary = new PopupMenu.PopupBaseMenuItem({
            reactive: false,
            can_focus: false,
        });
        const summaryLabel = new St.Label({ style_class: 'aium-summary' });
        if (!status) {
            summaryLabel.text = 'No data yet. Run "aium poll".';
        } else {
            const totals = status.totals ?? {};
            summaryLabel.text =
                `Spent this month: ${money(totals.spend_this_month, totals.currency)}\n` +
                `Balance: ${money(totals.balance, totals.currency)}`;
        }
        summary.add_child(summaryLabel);
        this._button.menu.addMenuItem(summary);

        if (status) {
            this._button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            const showZero = this._settings.get_boolean('show-zero-balance');
            for (const provider of status.providers ?? []) {
                if (!showZero && !isRelevant(provider))
                    continue;
                this._button.menu.addMenuItem(this._providerItem(provider));
            }
        }

        this._button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const refresh = new PopupMenu.PopupMenuItem('Refresh data');
        refresh.connect('activate', () => this._runPoll());
        this._button.menu.addMenuItem(refresh);

        const settingsItem = new PopupMenu.PopupMenuItem('Settings');
        settingsItem.connect('activate', () => this.openPreferences());
        this._button.menu.addMenuItem(settingsItem);
    }

    _providerItem(provider) {
        const url = provider.usage_url;
        const item = new PopupMenu.PopupBaseMenuItem({
            can_focus: !!url,
        });
        item.reactive = !!url;

        const box = new St.BoxLayout({ vertical: true, style_class: 'aium-provider' });
        const row = new St.BoxLayout();
        if (provider.peak != null) {
            const dot = new St.Widget({
                style_class: 'aium-peak-dot',
                style: `background-color: ${provider.peak ? '#e53935' : '#43a047'};`,
            });
            dot.y_align = Clutter.ActorAlign.CENTER;
            row.add_child(dot);
        }
        const name = new St.Label({
            text: provider.name ?? provider.id,
            style_class: 'aium-provider-name',
        });
        const detail = new St.Label({
            text: providerDetail(provider),
            style_class: 'aium-provider-detail',
        });
        name.x_expand = true;
        name.x_align = Clutter.ActorAlign.START;
        detail.x_align = Clutter.ActorAlign.END;
        row.add_child(name);
        row.add_child(detail);
        box.add_child(row);

        const spark = this._providerSpark(provider);
        if (spark)
            box.add_child(spark);

        item.add_child(box);

        if (url)
            item.connect('activate', () => this._openUri(url));
        return item;
    }

    _providerSpark(provider) {
        const values = provider.sparkline;
        if (!values || values.length < 2)
            return null;

        let color = [0.4, 0.6, 1.0];
        let max = null;
        if (provider.quota?.length) {
            const peak = Math.max(...provider.quota.map(w => w.utilization_pct));
            color = severityColor(peak);
            max = 100;
        }
        return new Sparkline(values, color, max);
    }

    _openUri(url) {
        Gio.AppInfo.launch_default_for_uri_async(url, null, null, (src, res) => {
            try {
                Gio.AppInfo.launch_default_for_uri_finish(res);
            } catch (e) {
                log(`aium: failed to open ${url}: ${e}`);
            }
        });
    }

    _runPoll() {
        try {
            Gio.Subprocess.new(
                [findAiumBinary(), 'poll'],
                Gio.SubprocessFlags.NONE,
            );
        } catch (e) {
            log(`aium: failed to run poll: ${e}`);
        }
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
            this._refresh();
            return GLib.SOURCE_REMOVE;
        });
    }

    disable() {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }
        this._tooltip?.destroy();
        this._tooltip = null;
        this._button?.destroy();
        this._button = null;
        this._settings = null;
    }
}
