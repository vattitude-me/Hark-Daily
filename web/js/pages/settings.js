// Settings tab: a full page mirroring the Android SettingsScreen.
// What's left is what still does something: the daily brief, the narrator, appearance and
// the account. The BYOK voice list and the AI-key panel went with the builder they served.
import { api, h, icon, toast, VOICES, voiceFor, EDITIONS } from '../api.js';
import { clipUrl } from '../storypack.js';
import {
  GlassGroup, Hairline, Hint, ListRow, Overline, PillButton, PillStepper,
  SectionLabel, Segmented, SwitchRow, Tag, applyPhotoMode,
} from '../design.js';
import {
  DeleteAccountSheet, SuggestSheet, enablePush, isIOS, isInstalled,
  pushSupported, requestNotificationPermission, subscribedWith,
} from '../sheets.js';

const speedLabel = (v) => `${Number(v).toFixed(2).replace(/0$/, '')}×`;

export class SettingsPage {
  constructor({ onDirty, goSources, email, setRate }) {
    this.onDirty = onDirty;
    this.goSources = goSources;
    this.email = email || '';
    this.setRate = setRate || (() => {});
    this.root = document.querySelector('#page-settings .screen');
    this.saved = null;
    this.draft = null;
    this.previewAudio = new Audio();
    this.deleteSheet = new DeleteAccountSheet();
    this.suggestSheet = new SuggestSheet();
    this.notes = null;      // today's greeting per voice, for the "hear it" buttons
    this.notesDay = null;
    this.loaded = false;
    this.pushHint = '';
    this.status = null;
  }

  async load() {
    if (this.loaded) return;
    const { settings } = await api.settings();
    const currentEd = window.state?.edition || 'ca';
    this.saved = { ...JSON.parse(JSON.stringify(settings)), edition: currentEd };
    this.draft = { ...JSON.parse(JSON.stringify(settings)), edition: currentEd };
    this.loaded = true;
    this.render();
    this.refreshPush();
  }

  reload() { this.loaded = false; return this.load(); }

  isDirty() {
    return this.loaded && JSON.stringify(this.saved) !== JSON.stringify(this.draft);
  }

  markDirty() { this.onDirty?.(); }

  set(patch) {
    Object.assign(this.draft, patch);
    this.markDirty();
    this.render();
  }

  async save() {
    const { edition: nextEd, ...settingsPayload } = this.draft;
    await api.saveSettings(settingsPayload);
    if (nextEd && nextEd !== window.state?.edition) {
      await window.setEdition?.(nextEd);
    }
    this.saved = JSON.parse(JSON.stringify(this.draft));
    applyPhotoMode(this.draft.color_photos);
    this.markDirty();
    this.render();
    toast('Settings saved.');
  }

  discard() {
    this.draft = JSON.parse(JSON.stringify(this.saved));
    this.markDirty();
    this.render();
  }

  /* ------------------------------------------------------------------ push */
  async refreshPush() {
    if (window.HarkNative) {
      this.pushOn = window.HarkNative.hasNotificationPermission();
      this.pushHint = this.pushOn
        ? 'Notifications are active for daily morning briefings.'
        : 'Enable notifications to receive daily morning alerts.';
      this.render();
      return;
    }
    const supported = pushSupported();
    if (!supported) {
      if (isIOS() && !isInstalled()) {
        this.pushHint = 'On iPhone & iPad, add Hark Daily to your Home Screen to enable morning notifications.';
      } else {
        this.pushHint = 'Notifications need HTTPS and a supported browser.';
      }
      this.pushOn = false;
      this.render();
      return;
    }
    try {
      const reg = await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      const granted = typeof Notification !== 'undefined' && Notification.permission === 'granted';
      if (granted && sub) {
        const status = await api.status().catch(() => ({}));
        if (status?.vapid_public_key) {
          this.status = status;
          if (subscribedWith(sub) !== status.vapid_public_key) {
            await enablePush(status.vapid_public_key);
            sub = await reg.pushManager.getSubscription();
          }
        }
      }
      this.pushOn = !!sub && granted;
    } catch { this.pushOn = false; }
    const permDenied = typeof Notification !== 'undefined' && Notification.permission === 'denied';
    if (permDenied) {
      this.pushHint = 'Notifications are blocked in this browser\u2019s site settings.';
    } else if (this.pushOn) {
      this.pushHint = 'You will be notified when your briefing is ready.';
    } else {
      this.pushHint = '';
    }
    this.render();
  }

  async setPush(on) {
    if (window.HarkNative) {
      if (on) {
        window.HarkNative.requestNotificationPermission();
        setTimeout(() => {
          this.pushOn = window.HarkNative.hasNotificationPermission();
          this.pushHint = this.pushOn
            ? 'Notifications are active for daily morning briefings.'
            : 'Notification permission was not granted.';
          this.render();
          if (this.pushOn) {
            toast('Notifications enabled! Daily briefings will alert your phone.');
            try {
              window.HarkNative.postNotification('Hark Daily', 'Daily briefing alerts are now enabled.');
            } catch (_) {}
          }
        }, 1200);
      } else {
        this.pushOn = false;
        this.pushHint = 'Turn off notifications in Android System Settings.';
        this.render();
        toast('To revoke notifications, update Hark Daily in Android App Settings.');
      }
      return;
    }

    if (!pushSupported()) {
      if (isIOS() && !isInstalled()) {
        document.getElementById('installSheet')?.showModal();
      } else {
        toast('Push notifications are not supported in this browser.', { error: true });
      }
      this.pushOn = false;
      this.render();
      return;
    }

    const isDenied = typeof Notification !== 'undefined' && Notification.permission === 'denied';
    if (on && isDenied) {
      this.pushHint = 'Notifications are blocked in this browser. Click the lock/tune icon in your address bar to allow them.';
      this.pushOn = false;
      this.render();
      toast('Notifications are blocked in browser settings. Please allow them via the address bar.', { error: true, ms: 6000 });
      return;
    }

    try {
      if (!on) {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) { await api.pushUnsubscribe(sub.toJSON()).catch(() => {}); await sub.unsubscribe().catch(() => {}); }
        this.pushOn = false;
        this.pushHint = '';
        this.render();
        toast('Notifications turned off.');
        return;
      }

      // Step 1: Request permission IMMEDIATELY while user tap gesture is active (critical for Safari/Chrome)
      const hasGranted = typeof Notification !== 'undefined' && Notification.permission === 'granted';
      if (!hasGranted) {
        const perm = await requestNotificationPermission();
        if (perm !== 'granted') {
          this.pushOn = false;
          this.pushHint = perm === 'denied'
            ? 'Notifications are blocked in this browser\u2019s site settings.'
            : 'Notification permission was not granted.';
          this.render();
          toast(this.pushHint, { error: true });
          return;
        }
      }

      // Step 2: Show immediate progress feedback
      this.pushHint = 'Setting up morning notifications…';
      const hintEl = document.getElementById('pushHint');
      if (hintEl) hintEl.textContent = this.pushHint;

      // Step 3: Fetch status key if not already cached
      const status = this.status?.vapid_public_key ? this.status : await api.status().catch(() => ({}));
      if (!status?.vapid_public_key) {
        this.pushOn = false;
        this.pushHint = 'Notifications are still setting up. Try again in a moment.';
        this.render();
        toast(this.pushHint, { error: true });
        return;
      }
      this.status = status;

      // Step 4: Register subscription
      await enablePush(status.vapid_public_key);
      this.pushOn = true;
      this.pushHint = 'You will be notified when your briefing is ready.';
      this.render();
      toast('Notifications enabled! A morning brief will nudge you when ready.');
    } catch (err) {
      this.pushOn = false;
      this.pushHint = err.message || "Couldn't enable notifications.";
      this.render();
      toast(err.message, { error: true, ms: 6000 });
    }
  }

  async testPush(btn) {
    btn.disabled = true;
    this.pushHint = 'Sending a test…';
    const hint = document.getElementById('pushHint');
    if (hint) hint.textContent = this.pushHint;
    if (window.HarkNative) {
      try {
        window.HarkNative.postNotification('Hark Daily Briefing', 'Test notification: Your morning brief is ready to listen!');
        this.pushHint = 'Test notification sent to device!';
        if (hint) hint.textContent = this.pushHint;
        toast('Test notification sent!');
      } catch (e) {
        this.pushHint = e.message;
        if (hint) hint.textContent = this.pushHint;
      } finally {
        btn.disabled = false;
      }
      return;
    }
    try {
      const r = await api.pushTest();
      this.pushHint = r.message || 'Sent.';
      if (hint) hint.textContent = this.pushHint;
    } catch (err) {
      this.pushHint = err.message;
      if (hint) hint.textContent = this.pushHint;
    } finally {
      btn.disabled = false;
    }
  }

  /* --------------------------------------------------------------- rendering */
  render() {
    if (!this.draft) return;
    const d = this.draft;
    const total = Object.values(d.stories || {}).reduce((n, v) => n + (Number(v) || 0), 0);
    this.root.replaceChildren(
      h('header', { class: 'screen-header' },
        h('div', { class: 'overline-row' }, Overline(d.daily ? 'Daily brief on' : 'Daily brief off')),
        h('h1', { class: 'display' }, 'Settings')),

      SectionLabel('Brief'),
      GlassGroup(
        SwitchRow('Make one every morning', d.daily, { onChange: (on) => this.set({ daily: on }) }),
        Hairline(),
        SwitchRow('Notify this device when it\u2019s ready', !!this.pushOn, {
          detail: 'A morning nudge when your briefing is done',
          onChange: (on) => this.setPush(on),
        }),
        h('div', { class: 'push-test-row hidden', id: 'pushRow' },
          PillButton('Send a test notification', { filled: false, onClick: (e) => this.testPush(e.currentTarget) })),
        h('p', { class: 'hint', id: 'pushHint' }, this.pushHint || ''),
        Hairline(),
        ListRow({
          label: 'Topics and story counts',
          value: total ? `${total} stories` : 'None yet',
          caret: true,
          onClick: () => this.goSources(),
        }),
      ),

      SectionLabel('Regional Edition'),
      GlassGroup(
        ListRow({
          label: 'News Country',
          detail: 'National top stories, politics, and sports tailored for your country. AI, Tech, and Science are shared universally.',
          end: Tag(EDITIONS[d.edition || window.state?.edition] ? `${(EDITIONS[d.edition || window.state?.edition].code || 'CA').toUpperCase()} · ${EDITIONS[d.edition || window.state?.edition].name.toUpperCase()}` : 'CA · CANADA'),
          caret: true,
          onClick: () => {
            const current = d.edition || window.state?.edition || 'ca';
            const order = ['ca', 'us', 'in'];
            const next = order[(order.indexOf(current) + 1) % order.length];
            this.set({ edition: next });
          },
        }),
      ),

      SectionLabel('Podcast & Playback'),
      this.voiceGroup(d),

      SectionLabel('Appearance'),
      this.appearanceGroup(d),

      SectionLabel('Upcoming Features', { detail: 'In active development for future updates' }),
      this.upcomingFeaturesGroup(),

      SectionLabel('Privacy & Analytics'),
      GlassGroup(
        ListRow({
          label: 'Analytics Cookies',
          detail: 'Anonymous search queries and playback telemetry used to improve daily briefings.',
          end: Tag((() => {
            try { return localStorage.getItem('hark-consent') === 'granted' ? 'ACCEPTED' : 'REJECTED'; } catch (e) { return 'REJECTED'; }
          })()),
          caret: true,
          onClick: () => {
            const current = (() => {
              try { return localStorage.getItem('hark-consent') === 'granted'; } catch (e) { return false; }
            })();
            const next = current ? 'denied' : 'granted';
            try { localStorage.setItem('hark-consent', next); } catch (e) {}
            window.gtag?.('consent', 'update', { 'analytics_storage': next });
            toast(next === 'granted' ? 'Analytics cookies accepted ✓' : 'Analytics cookies rejected');
            this.render();
          },
        }),
      ),

      SectionLabel('Account'),
      this.email ? GlassGroup(
        ListRow({ label: this.email, end: Tag('SYNCED') }),
        Hairline(),
        ListRow({ label: 'Sign out', color: 'var(--err)', onClick: async () => { await api.signOut(); location.reload(); } }),
        Hairline(),
        ListRow({ label: 'Delete account', color: 'var(--err)', onClick: () => this.openDelete() }),
      ) : GlassGroup(
        ListRow({
          label: 'Sign in to Hark Daily',
          end: Tag('GUEST'),
          caret: true,
          onClick: () => window.openSignIn?.('settings'),
        }),
      ),
      !this.email ? h('p', { class: 'hint' }, 'Sign in free with Google or email to sync your preferences and sources with the Android app.') : null,

      h('div', { class: 'legal-row' },
        h('span', { class: 'footer-attribution' },
          'Created and managed by ',
          h('a', { href: 'https://vattitude.ca', target: '_blank', rel: 'noopener' }, 'vattitude.ca')
        ),
        h('span', { class: 'footer-sep', 'aria-hidden': 'true' }, '·'),
        h('a', { href: '/privacy', target: '_blank', rel: 'noopener' }, 'Privacy'),
        h('span', { class: 'footer-sep', 'aria-hidden': 'true' }, '·'),
        h('a', { href: '/terms', target: '_blank', rel: 'noopener' }, 'Terms')),
    );
    // Push test row visibility depends on push state.
    const pr = document.getElementById('pushRow');
    if (pr) pr.classList.toggle('hidden', !this.pushOn);
  }

  /**
   * Podcast & Playback settings: shows the active co-host pair (Matthew & Kelly)
   * and playback speed controls.
   */
  voiceGroup(d) {
    const speed = Math.round((Number(d.speed) || 1.0) * 20);
    return GlassGroup(
      ListRow({
        label: 'Podcast Hosts',
        detail: 'Daily two-host conversation & news analysis across every story.',
        end: Tag('MATTHEW & KELLY', 'accent'),
      }),
      Hairline(),
      ListRow({
        label: 'Playback speed',
        end: PillStepper(speedLabel(speed / 20), {
          canLower: speed > 16, canRaise: speed < 26,
          lowerLabel: 'Slower', raiseLabel: 'Faster',
          onLower: () => this.setSpeed((speed - 1) / 20),
          onRaise: () => this.setSpeed((speed + 1) / 20),
        }),
      }),
    );
  }

  /** Speed is something you can hear straight away, so it doesn't wait for Save. */
  setSpeed(v) {
    const speed = Math.max(0.8, Math.min(1.3, Math.round(v * 100) / 100));
    this.set({ speed });
    this.setRate(speed);
  }

  /** Play today's greeting in a voice: the real recording, so what you hear is what you get. */
  async preview(voice) {
    const a = this.previewAudio;
    a.pause();
    try {
      const today = new Date().toLocaleDateString('en-CA');
      if (this.notesDay !== today || !this.notes) {
        this.notes = await api.voiceNotes(today);
        this.notesDay = today;
      }
      const note = this.notes.find((n) => n.voice === voice.id && n.note_key === 'greeting_morning');
      if (!note) throw new Error(`${voice.name}'s recording for today isn't ready yet. Try again in a few minutes.`);
      a.src = clipUrl(note.audio_path);
      await a.play();
    } catch (err) {
      toast(err.message, { error: true });
    }
  }

  appearanceGroup(d) {
    let stored = null;
    try { stored = localStorage.getItem('mb-theme'); } catch { /* ignore */ }
    const seg = Segmented(['Light', 'Dark', 'System'],
      stored === 'dark' ? 1 : stored === 'system' ? 2 : 0,
      {
        glass: true,
        onSelect: (i) => {
          const pref = ['light', 'dark', 'system'][i];
          const resolved = pref === 'system'
            ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : pref;
          document.documentElement.dataset.theme = resolved;
          try {
            if (pref === 'system') localStorage.removeItem('mb-theme');
            else localStorage.setItem('mb-theme', pref);
          } catch { /* ignore */ }
          document.dispatchEvent(new CustomEvent('mb-theme', { detail: pref }));
        },
      });
    return h('div', { class: 'appearance-section' }, seg,
      GlassGroup(SwitchRow('Color story photos', d.color_photos !== false, {
        detail: 'Cover and thumbnails in full color',
        onChange: (on) => this.set({ color_photos: on }),
      })));
  }

  upcomingFeaturesGroup() {
    return GlassGroup(
      ListRow({
        label: 'New News Sources & Feeds',
        detail: 'Substack newsletters, financial market desks, indie tech blogs, and custom RSS link feeds.',
        end: Tag('IN PROGRESS', 'tech'),
        onClick: () => this.openSuggest('News Source'),
      }),
      Hairline(),
      ListRow({
        label: 'Guest Co-Hosts & Special Editions',
        detail: 'Curated guest analysts and regional accents joining Matthew & Kelly powered by Chatterbox-Turbo.',
        end: Tag('PREVIEW', 'warn'),
        onClick: () => this.openSuggest('New Voice'),
      }),
      Hairline(),
      ListRow({
        label: 'Custom Voice Capabilities',
        detail: 'Train personal voice clones or upload reference audio to hear briefings delivered in custom sound styles.',
        end: Tag('SOON', 'custom'),
        onClick: () => this.openSuggest('Custom Voice / Styles'),
      }),
      Hairline(),
      ListRow({
        label: 'Interactive Voice Q&A',
        detail: 'Ask follow-up questions and explore stories deeper during playback with Gemini streaming voice AI.',
        end: Tag('ROADMAP', 'accent'),
        onClick: () => this.openSuggest('Feature Idea'),
      }),
      Hairline(),
      h('div', { class: 'suggest-callout-row' },
        h('div', { class: 'suggest-callout-text' },
          h('span', { class: 'suggest-title' }, 'Have a favorite voice or publication?'),
          h('span', { class: 'suggest-sub' }, 'Tell us what you want to hear next in Hark Daily.')),
        PillButton('Suggest an idea', {
          filled: false,
          onClick: () => this.openSuggest('News Source'),
        })
      )
    );
  }

  openSuggest(category = 'News Source') {
    this.suggestSheet.open(category);
  }

  openDelete() {
    this.deleteSheet.open(this.email);
  }
}
