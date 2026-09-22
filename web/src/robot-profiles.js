/** Presentation only: choosing a model never changes replay evidence. */
export const ROBOT_PROFILES = Object.freeze([
  { id: "rover", label: "Ровер", description: "Колёсная платформа" },
  { id: "quadruped", label: "Робопёс", description: "Четыре опоры" },
  { id: "humanoid", label: "Гуманоид", description: "Две опоры" },
]);

export function visualProfile(replay, override = null) {
  const profile = override ?? replay?.robot?.visual_profile;
  return ROBOT_PROFILES.some(({ id }) => id === profile) ? profile : "rover";
}

// Small, local vector illustrations; no network images or runtime telemetry.
export function profileIllustration(profile) {
  const shapes = {
    rover: `<g fill="#202a3a" stroke="#526077" stroke-width="2"><ellipse cx="30" cy="54" rx="10" ry="13"/><ellipse cx="82" cy="47" rx="10" ry="13"/><ellipse cx="72" cy="67" rx="10" ry="13"/><ellipse cx="18" cy="65" rx="10" ry="13"/></g><path d="m18 36 34-14 43 16-36 16z" fill="#f4f6fb" stroke="#c3cbda"/><path d="m18 36 41 18v16L18 53z" fill="#abb8cb"/><path d="m59 54 36-16v16L59 70z" fill="#dbe2ed"/><path d="m22 47 32 14v4L22 51z" fill="#4d78ff"/><path d="m65 59 23-10v6l-23 10z" fill="#263347"/><path d="M54 31V17" stroke="#8796ae" stroke-width="5"/><ellipse cx="54" cy="16" rx="10" ry="5" fill="#24334c"/><ellipse cx="54" cy="13" rx="10" ry="4" fill="#527bff"/><g fill="#899bb8"><ellipse cx="18" cy="65" rx="4" ry="7"/><ellipse cx="72" cy="67" rx="4" ry="7"/></g>`,
    quadruped: `<g fill="none" stroke-linejoin="round" stroke-linecap="round"><path d="m32 41-6 19 10 11M78 34l-3 19 13 11" stroke="#687993" stroke-width="7"/><path d="m46 49-7 17 12 14M88 44l-5 16 12 12" stroke="#d2dbe9" stroke-width="8"/><path d="m46 49-7 17M88 44l-5 16" stroke="#657a9c" stroke-width="3"/></g><path d="m25 32 32-13 35 14-32 14z" fill="#eff3fa"/><path d="m25 32 35 15v13L25 45z" fill="#acbbd0"/><path d="m60 47 32-14v13L60 60z" fill="#d4deed"/><path d="m30 41 24 10v4L30 45z" fill="#4d78ff"/><path d="m81 27 19 6v16l-19-6z" fill="#263347"/><circle cx="93" cy="38" r="3" fill="#6a99ff"/><g fill="#283951"><circle cx="46" cy="51" r="5"/><circle cx="85" cy="44" r="5"/></g>`,
    humanoid: `<g stroke="#536b90" stroke-width="8" stroke-linecap="round"><path d="m44 35-9 14 2 13m35-27 10 13-2 13"/></g><path d="m43 28 17-5 15 8-6 29H47z" fill="#dce4f0"/><path d="m44 32 14 4v20l-10-3z" fill="#a5b6cc"/><path d="m50 39 13 4 4-9-13-4z" fill="#4d78ff"/><path d="m48 59-2 16-2 9m21-25 3 16 4 9" fill="none" stroke="#cad6e7" stroke-width="10" stroke-linecap="round"/><path d="m43 86 12 1m15-1 12 1" stroke="#263347" stroke-width="6" stroke-linecap="round"/><rect x="47" y="7" width="24" height="19" rx="7" fill="#dae3f0"/><path d="M51 14h16v7H51z" fill="#21334e"/><path d="M54 17h10" stroke="#729cff" stroke-width="2"/><g fill="#4d6389"><circle cx="47" cy="72" r="4"/><circle cx="68" cy="73" r="4"/></g>`,
  };
  return `<svg class="profile-illustration" viewBox="0 0 112 96" aria-hidden="true"><ellipse cx="57" cy="84" rx="43" ry="7" fill="#263347" opacity=".09"/>${shapes[profile] ?? shapes.rover}</svg>`;
}

export function topRobotIllustration(profile, color) {
  const body = {
    rover: `<g fill="#1b2639" stroke="#8c9db6" stroke-width="1"><rect x="-13" y="-15" width="10" height="8" rx="2"/><rect x="5" y="-15" width="10" height="8" rx="2"/><rect x="-13" y="7" width="10" height="8" rx="2"/><rect x="5" y="7" width="10" height="8" rx="2"/></g><rect x="-15" y="-10" width="31" height="20" rx="5" fill="#dbe5f3" stroke="#9caec8"/><path d="M-11-6h21v12h-21z" fill="#a6b8d0"/><path d="M13-7v14" stroke="${color}" stroke-width="3"/><circle cx="-4" cy="0" r="5" fill="#233754" stroke="${color}" stroke-width="2"/>`,
    quadruped: `<path d="M-9-6-16-15-6-18M10-6l7-9-9-3M-9 6l-7 9 10 3M10 6l7 9-9 3" fill="none" stroke="#bbcbe0" stroke-width="4" stroke-linejoin="round"/><rect x="-16" y="-7" width="30" height="14" rx="5" fill="#dae5f5"/><path d="M-10 0H8" stroke="${color}" stroke-width="4"/><rect x="10" y="-5" width="9" height="10" rx="3" fill="#263852" stroke="#9db2cf"/>`,
    humanoid: `<path d="M-3-8-3-16 7-17M-3 8-3 16 7 17" fill="none" stroke="#c9d9ed" stroke-width="5" stroke-linecap="round"/><rect x="-8" y="-11" width="13" height="22" rx="5" fill="#9aafca"/><rect x="1" y="-7" width="12" height="14" rx="5" fill="#e7effa"/><path d="M11-4v8" stroke="${color}" stroke-width="3"/>`,
  };
  return `<ellipse rx="23" ry="21" fill="#07111f" opacity=".35"/>${body[profile] ?? body.rover}`;
}
