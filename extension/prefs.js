import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import { ExtensionPreferences } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class AiumPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage();
        window.add(page);

        const group = new Adw.PreferencesGroup({ title: 'Panel' });
        page.add(group);

        const metrics = [
            { label: 'Monthly spend', value: 'spend_month' },
            { label: 'Daily spend', value: 'spend_today' },
            { label: 'Balance', value: 'balance' },
            { label: 'None (hide)', value: 'none' },
        ];

        const metricCombo = (title, subtitle, key) => {
            const list = new Gtk.StringList();
            for (const metric of metrics)
                list.append(metric.label);
            const combo = new Adw.ComboRow({
                title,
                subtitle,
                model: list,
            });
            const index = metrics.findIndex(m => m.value === settings.get_string(key));
            combo.selected = index >= 0 ? index : 0;
            combo.connect('notify::selected', () => {
                settings.set_string(key, metrics[combo.selected].value);
            });
            return combo;
        };

        group.add(metricCombo('Top line', 'Left/top metric in the panel', 'top-metric'));
        group.add(metricCombo('Bottom line', 'Right/bottom metric in the panel', 'bottom-metric'));

        const showZero = new Adw.SwitchRow({
            title: 'Show zero-balance providers',
            subtitle: 'List providers with no balance and no monthly spend',
        });
        settings.bind(
            'show-zero-balance', showZero, 'active', Gio.SettingsBindFlags.DEFAULT,
        );
        group.add(showZero);

        const showLabel = new Adw.SwitchRow({
            title: 'Show summary label',
            subtitle: 'Show the spend/balance text next to the panel icon',
        });
        settings.bind(
            'show-label', showLabel, 'active', Gio.SettingsBindFlags.DEFAULT,
        );
        group.add(showLabel);

        const spin = new Adw.SpinRow({
            title: 'Refresh interval',
            subtitle: 'Seconds between status cache reads',
            adjustment: new Gtk.Adjustment({
                lower: 5,
                upper: 3600,
                step_increment: 5,
                page_increment: 30,
            }),
        });
        spin.value = settings.get_int('refresh-interval-seconds');
        spin.connect('notify::value', () => {
            settings.set_int('refresh-interval-seconds', Math.round(spin.value));
        });
        group.add(spin);
    }
}
