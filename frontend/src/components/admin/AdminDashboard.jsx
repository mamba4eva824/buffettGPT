import { useState, useEffect, useCallback } from 'react';
import { adminApi } from '../../api/adminApi';

// ── Collapsible Card ──────────────────────────────────────────────
function Card({ title, icon, color, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);

  const colorMap = {
    gold:   { border: 'border-vi-gold/40',   bg: 'bg-vi-gold/10',   text: 'text-vi-gold',   hover: 'hover:bg-vi-gold/20' },
    sage:   { border: 'border-vi-sage/40',   bg: 'bg-vi-sage/10',   text: 'text-vi-sage',   hover: 'hover:bg-vi-sage/20' },
    purple: { border: 'border-[#6d28d9]/40', bg: 'bg-[#6d28d9]/10', text: 'text-[#6d28d9]', hover: 'hover:bg-[#6d28d9]/20' },
    rose:   { border: 'border-vi-rose/40',   bg: 'bg-vi-rose/10',   text: 'text-vi-rose',   hover: 'hover:bg-vi-rose/20' },
  };
  const c = colorMap[color] || colorMap.gold;

  return (
    <div className={`rounded-xl border ${c.border} bg-sand-50 dark:bg-warm-900 overflow-hidden transition-all`}>
      <button
        onClick={() => setOpen(!open)}
        className={`w-full flex items-center gap-3 px-5 py-3.5 ${c.hover} transition-colors`}
      >
        <span className={`material-symbols-outlined text-lg ${c.text}`}>{icon}</span>
        <span className={`font-serif font-bold text-sm tracking-wide ${c.text}`}>{title}</span>
        <span className="flex-1" />
        <span className={`material-symbols-outlined text-base text-sand-400 dark:text-warm-300 transition-transform ${open ? 'rotate-180' : ''}`}>
          expand_more
        </span>
      </button>
      {open && (
        <div className="px-5 pb-5 pt-1 border-t border-sand-200 dark:border-warm-800">
          {children}
        </div>
      )}
    </div>
  );
}

// ── Field Components ──────────────────────────────────────────────
function NumberField({ label, value, onChange, step, min, max }) {
  return (
    <label className="flex items-center justify-between gap-4 py-1.5">
      <span className="text-xs font-semibold text-sand-600 dark:text-warm-200 tracking-wide">{label}</span>
      <input
        type="number"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        step={step}
        min={min}
        max={max}
        className="w-28 bg-sand-100 dark:bg-warm-800 border border-sand-200 dark:border-warm-700 rounded-lg px-3 py-1.5 text-xs font-mono text-sand-800 dark:text-warm-50 focus:outline-none focus:ring-2 focus:ring-vi-gold/50 focus:border-vi-gold text-right transition-all"
      />
    </label>
  );
}

function ToggleField({ label, value, onChange }) {
  return (
    <label className="flex items-center justify-between gap-4 py-1.5 cursor-pointer">
      <span className="text-xs font-semibold text-sand-600 dark:text-warm-200 tracking-wide">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors ${
          value ? 'bg-vi-sage' : 'bg-sand-300 dark:bg-warm-700'
        }`}
      >
        <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform mt-0.5 ${
          value ? 'translate-x-[18px]' : 'translate-x-0.5'
        }`} />
      </button>
    </label>
  );
}

// ── Section Renderers ─────────────────────────────────────────────
function TokenLimitsSection({ data, onUpdate }) {
  const update = (key, val) => onUpdate('token_limits', { ...data, [key]: val });
  const updateFollowup = (key, val) =>
    onUpdate('token_limits', { ...data, followup_access: { ...data.followup_access, [key]: val } });

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-6">
        <NumberField label="Plus" value={data.plus} onChange={(v) => update('plus', v)} step={100000} min={0} />
        <NumberField label="Free" value={data.free} onChange={(v) => update('free', v)} step={10000} min={0} />
        <NumberField label="Default Fallback" value={data.default_fallback} onChange={(v) => update('default_fallback', v)} step={10000} min={0} />
      </div>
      <div className="pt-2 border-t border-sand-200 dark:border-warm-800">
        <p className="text-[10px] uppercase tracking-widest text-sand-400 dark:text-warm-300 font-bold mb-2">Follow-up Access</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-6">
          <NumberField label="Anonymous" value={data.followup_access.anonymous} onChange={(v) => updateFollowup('anonymous', v)} step={100000} min={0} />
          <NumberField label="Free" value={data.followup_access.free} onChange={(v) => updateFollowup('free', v)} step={100000} min={0} />
          <NumberField label="Plus" value={data.followup_access.plus} onChange={(v) => updateFollowup('plus', v)} step={100000} min={0} />
        </div>
      </div>
    </div>
  );
}

function RateLimitsSection({ data, onUpdate }) {
  const update = (key, val) => onUpdate('rate_limits', { ...data, [key]: val });
  const updateTier = (tier, key, val) =>
    onUpdate('rate_limits', { ...data, tiered: { ...data.tiered, [tier]: { ...data.tiered[tier], [key]: val } } });

  const tierColors = { anonymous: 'text-sand-500', authenticated: 'text-vi-gold', premium: 'text-vi-sage', enterprise: 'text-[#6d28d9]' };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-6">
        <NumberField label="Anonymous Monthly" value={data.anonymous_monthly} onChange={(v) => update('anonymous_monthly', v)} min={0} />
        <NumberField label="Authenticated Monthly" value={data.authenticated_monthly} onChange={(v) => update('authenticated_monthly', v)} min={0} />
        <NumberField label="Grace Period (hrs)" value={data.grace_period_hours} onChange={(v) => update('grace_period_hours', v)} min={0} step={0.5} />
      </div>
      <div className="pt-2 border-t border-sand-200 dark:border-warm-800">
        <p className="text-[10px] uppercase tracking-widest text-sand-400 dark:text-warm-300 font-bold mb-2">Tiered Rates</p>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-sand-400 dark:text-warm-300 text-left">
                <th className="pb-1 pr-3 font-semibold">Tier</th>
                <th className="pb-1 pr-3 font-semibold">Daily</th>
                <th className="pb-1 pr-3 font-semibold">Hourly</th>
                <th className="pb-1 pr-3 font-semibold">Per Min</th>
                <th className="pb-1 pr-3 font-semibold">Burst</th>
                <th className="pb-1 font-semibold">Session TTL (hrs)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.tiered).map(([tier, vals]) => (
                <tr key={tier} className="border-t border-sand-100 dark:border-warm-800">
                  <td className={`py-1.5 pr-3 font-bold capitalize ${tierColors[tier] || ''}`}>{tier}</td>
                  {['daily', 'hourly', 'per_minute', 'burst', 'session_ttl_hours'].map((field) => (
                    <td key={field} className="py-1.5 pr-3">
                      <input
                        type="number"
                        value={vals[field] ?? ''}
                        onChange={(e) => updateTier(tier, field, e.target.value === '' ? '' : Number(e.target.value))}
                        className="w-16 bg-sand-100 dark:bg-warm-800 border border-sand-200 dark:border-warm-700 rounded px-2 py-1 text-[11px] font-mono text-sand-800 dark:text-warm-50 focus:outline-none focus:ring-1 focus:ring-vi-gold/50 text-right"
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ModelConfigSection({ data, onUpdate }) {
  const update = (key, val) => onUpdate('model_config', { ...data, [key]: val });

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
      <NumberField label="Follow-up Temp" value={data.followup_temperature} onChange={(v) => update('followup_temperature', v)} step={0.1} min={0} max={2} />
      <NumberField label="Follow-up Max Tokens" value={data.followup_max_tokens} onChange={(v) => update('followup_max_tokens', v)} step={256} min={1} />
      <NumberField label="Market Intel Temp" value={data.market_intel_temperature} onChange={(v) => update('market_intel_temperature', v)} step={0.1} min={0} max={2} />
      <NumberField label="Market Intel Max Tokens" value={data.market_intel_max_tokens} onChange={(v) => update('market_intel_max_tokens', v)} step={256} min={1} />
      <NumberField label="Max Orchestration Turns" value={data.max_orchestration_turns} onChange={(v) => update('max_orchestration_turns', v)} min={1} max={50} />
    </div>
  );
}

function FeatureFlagsSection({ data, onUpdate }) {
  const update = (key, val) => onUpdate('feature_flags', { ...data, [key]: val });

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
      <ToggleField label="Enable Rate Limiting" value={data.enable_rate_limiting} onChange={(v) => update('enable_rate_limiting', v)} />
      <ToggleField label="Enable Device Fingerprinting" value={data.enable_device_fingerprinting} onChange={(v) => update('enable_device_fingerprinting', v)} />
    </div>
  );
}

function NotificationThresholdsSection({ data, onUpdate }) {
  const update = (key, val) => onUpdate('notification_thresholds', { ...data, [key]: val });

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
      <NumberField label="Warning %" value={data.warning_percent} onChange={(v) => update('warning_percent', v)} min={0} max={100} />
      <NumberField label="Critical %" value={data.critical_percent} onChange={(v) => update('critical_percent', v)} min={0} max={100} />
    </div>
  );
}

function ReferralTiersSection({ data, onUpdate }) {
  const updateTier = (idx, key, val) => {
    const next = data.map((t, i) => (i === idx ? { ...t, [key]: val } : t));
    onUpdate('referral_tiers', next);
  };
  const addTier = () => onUpdate('referral_tiers', [...data, { threshold: 1, trial_days: 7 }]);
  const removeTier = (idx) => onUpdate('referral_tiers', data.filter((_, i) => i !== idx));

  return (
    <div className="space-y-2">
      {data.map((tier, idx) => (
        <div key={idx} className="flex items-center gap-4">
          <NumberField label="Referrals" value={tier.threshold} onChange={(v) => updateTier(idx, 'threshold', v)} min={1} />
          <NumberField label="Trial Days" value={tier.trial_days} onChange={(v) => updateTier(idx, 'trial_days', v)} min={1} />
          <button
            onClick={() => removeTier(idx)}
            className="text-vi-rose/70 hover:text-vi-rose transition-colors mt-1"
          >
            <span className="material-symbols-outlined text-base">close</span>
          </button>
        </div>
      ))}
      <button
        onClick={addTier}
        className="flex items-center gap-1.5 text-[11px] font-semibold text-vi-gold hover:text-vi-gold/80 transition-colors mt-1"
      >
        <span className="material-symbols-outlined text-sm">add_circle</span>
        Add Tier
      </button>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────
export default function AdminDashboard() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState(null);
  const [lastSaved, setLastSaved] = useState(null);

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await adminApi.getSettings(null);
      setSettings(res.settings);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  const handleUpdate = useCallback(async (category, values) => {
    setSettings((prev) => ({ ...prev, [category]: values }));
    try {
      setSaving(category);
      await adminApi.updateSettings(null, category, values);
      setLastSaved(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(null);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-sand-50 dark:bg-warm-950">
        <div className="flex items-center gap-3 text-vi-gold">
          <span className="material-symbols-outlined animate-spin">progress_activity</span>
          <span className="text-sm font-semibold">Loading settings...</span>
        </div>
      </div>
    );
  }

  if (error && !settings) {
    return (
      <div className="flex items-center justify-center h-full bg-sand-50 dark:bg-warm-950">
        <div className="text-center space-y-3">
          <span className="material-symbols-outlined text-3xl text-vi-rose">error</span>
          <p className="text-sm text-vi-rose font-semibold">{error}</p>
          <button onClick={loadSettings} className="text-xs text-vi-gold hover:underline">Retry</button>
        </div>
      </div>
    );
  }

  const SECTIONS = [
    { key: 'token_limits', title: 'Token Limits', icon: 'generating_tokens', color: 'gold', Component: TokenLimitsSection, defaultOpen: true },
    { key: 'rate_limits', title: 'Rate Limits', icon: 'speed', color: 'sage', Component: RateLimitsSection },
    { key: 'model_config', title: 'Model Configuration', icon: 'tune', color: 'purple', Component: ModelConfigSection },
    { key: 'feature_flags', title: 'Feature Flags', icon: 'toggle_on', color: 'sage', Component: FeatureFlagsSection },
    { key: 'notification_thresholds', title: 'Notification Thresholds', icon: 'notifications_active', color: 'rose', Component: NotificationThresholdsSection },
    { key: 'referral_tiers', title: 'Referral Tiers', icon: 'loyalty', color: 'purple', Component: ReferralTiersSection },
  ];

  return (
    <div className="flex flex-col h-full bg-sand-50 dark:bg-warm-950 text-sand-800 dark:text-warm-50 overflow-hidden">
      {/* Header */}
      <div className="shrink-0 border-b border-sand-200 dark:border-warm-800 bg-sand-50 dark:bg-warm-950 px-5 md:px-8 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-xl text-vi-gold">admin_panel_settings</span>
            <h1 className="font-serif font-bold text-lg text-vi-gold tracking-wide">Admin Dashboard</h1>
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            {saving && (
              <span className="flex items-center gap-1.5 text-vi-gold">
                <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                Saving {saving}...
              </span>
            )}
            {lastSaved && !saving && (
              <span className="text-vi-sage flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">check_circle</span>
                Saved {lastSaved}
              </span>
            )}
            {error && settings && (
              <span className="text-vi-rose flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">warning</span>
                {error}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 md:px-8 py-5 space-y-3">
        {SECTIONS.map(({ key, title, icon, color, Component, defaultOpen }) => (
          <Card key={key} title={title} icon={icon} color={color} defaultOpen={defaultOpen}>
            <Component data={settings[key]} onUpdate={handleUpdate} />
          </Card>
        ))}
      </div>
    </div>
  );
}
