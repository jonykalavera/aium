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

        const modes = [
            { label: 'Both (spend over balance)', value: 'both' },
            { label: 'Spend only', value: 'spend' },
            { label: 'Balance only', value: 'balance' },
        ];
        const list = new Gtk.StringList();
        for (const mode of modes)
            list.append(mode.label);
        const combo = new Adw.ComboRow({
            title: 'Panel summary',
            subtitle: 'What the panel indicator shows',
            model: list,
        });
        const selectMode = value => {
            const index = modes.findIndex(mode => mode.value === value);
            return index >= 0 ? index : 0;
        };
        combo.selected = selectMode(settings.get_string('summary-mode'));
        combo.connect('notify::selected', () => {
            settings.set_string('summary-mode', modes[combo.selected].value);
        });
        group.add(combo);

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
