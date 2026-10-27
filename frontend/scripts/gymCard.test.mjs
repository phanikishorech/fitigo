import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'

globalThis.__gymCardReact = React
const source = readFileSync(new URL('../src/components/gym/GymCard.tsx', import.meta.url), 'utf8')
const code = ts.transpileModule(source
  .replace(/import Icon[^\r\n]+/, `const React=globalThis.__gymCardReact;const Icon=({name})=>React.createElement('span',{'data-icon':name});`)
  .replace(/import \{ Badge, Image, Link \}[^\r\n]+/, `
    const Badge=({children})=>React.createElement('span',null,children);
    const Image=({src,alt})=>React.createElement('img',{src,alt});
    const Link=({to,label,children,className})=>React.createElement('a',{href:to,'aria-label':label,className},children);
  `), { compilerOptions: { jsx: ts.JsxEmit.React, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { default: GymCard } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const gym = { gym_id: 42, gym_name: 'Test Gym', primary_image: '/gym.jpg', is_featured: true,
  average_rating: 4.5, review_count: 12, is_open_now: true, locality: 'Locality', city: 'City',
  distance_km: 1.2, facilities: [{ id: 1, name: 'Showers' }], membership_access_status: 'INCLUDED' }

test('gym cards render without a saving button or unavailable popup', () => {
  const html = renderToStaticMarkup(React.createElement(GymCard, { gym }))
  assert.doesNotMatch(html, /<button|fg-favorite|data-icon="heart"|Keep this gym in mind|About saving|role="dialog"/)
  assert.doesNotMatch(source, /favoritesService|setNotice|Modal/)
})
test('gym images, navigation, ratings, facilities and optional actions remain', () => {
  const html = renderToStaticMarkup(React.createElement(GymCard, { gym,
    action: React.createElement('a', { href: '/my-access' }, 'Visit this gym') }))
  for (const expected of ['href="/gyms/42"', 'alt="Test Gym"', 'FITIGO SELECT', '4.5', '(12)', 'Showers', 'Included in your plan', 'Visit this gym']) assert.ok(html.includes(expected), expected)
})