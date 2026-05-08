#!/usr/bin/env python3
"""Génère tous les logos Nseek : standard, ciel (splash), marine."""
import os
import cairosvg

os.makedirs(os.path.expanduser('~/Programmes/assets'), exist_ok=True)

# ── Logo standard (GitHub, thème clair) ──────────────────────────────────────
svg_standard = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 330">
<defs>
<linearGradient id="wg" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" stop-color="#5ab4f0"/><stop offset="100%" stop-color="#1a6bb5"/></linearGradient>
<linearGradient id="wb" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" stop-color="#7ecbff"/><stop offset="100%" stop-color="#4aaee0"/></linearGradient>
</defs>
<g transform="translate(10,20)">
<path d="M55 95C40 78 22 70 15 80C12 90 22 102 38 106C45 108 52 104 55 95Z" fill="url(#wg)"/>
<path d="M55 105C42 118 28 122 18 116C12 110 18 98 35 96C44 94 52 98 55 105Z" fill="url(#wg)"/>
<path d="M54 100C65 100 80 98 95 96" fill="none" stroke="#083060" stroke-width="12" stroke-linecap="round"/>
<path d="M88 97C100 80 125 62 162 52C198 42 240 44 272 60C300 74 316 100 316 126C316 152 302 174 278 186C260 196 238 198 218 194C200 190 185 180 176 168Z" fill="url(#wg)"/>
<path d="M102 94C122 80 150 70 182 64C214 58 246 62 268 76C288 90 298 112 296 136C294 158 280 176 260 184C242 190 220 190 204 184C188 178 176 166 168 152C150 128 120 108 102 94Z" fill="url(#wb)" opacity="0.65"/>
<path d="M202 46C209 24 220 10 230 14C226 26 218 38 210 48Z" fill="#083060"/>
<path d="M148 70C124 60 100 64 88 78C98 88 122 86 142 80Z" fill="#083060"/>
<path d="M218 194C232 200 248 198 260 190C272 182 280 168 276 154C272 142 260 136 248 138C260 146 266 160 260 172C254 184 238 192 218 194Z" fill="url(#wg)"/>
<path d="M238 182C249 192 262 192 270 186" fill="none" stroke="#c8eaff" stroke-width="3.5" stroke-linecap="round"/>
<circle cx="258" cy="152" r="7.5" fill="#dff0ff"/>
<circle cx="259.5" cy="152" r="4.2" fill="#040e1e"/>
<circle cx="261" cy="150" r="1.6" fill="white"/>
<path d="M229 46C228 32 226 16 224 4C228 16 230 8 231 0C232 8 234 16 236 4C235 16 233 32 231 46Z" fill="#7ecbff" opacity="0.9"/>
<path d="M224 42C214 28 202 16 194 10C198 20 196 14 199 9C203 15 208 24 214 36Z" fill="#90d8ff" opacity="0.7"/>
<path d="M236 42C246 28 258 16 266 10C262 20 264 14 261 9C257 15 252 24 246 36Z" fill="#90d8ff" opacity="0.7"/>
</g>
<text x="358" y="158" font-family="sans-serif" font-weight="bold" font-size="88" letter-spacing="-2" fill="#1a6bb5">Nseek</text>
<text x="361" y="192" font-family="sans-serif" font-size="17" fill="#4a9fd4">client IA natif Linux</text>
<rect x="361" y="200" width="185" height="2" rx="1" fill="#2d8fe0" opacity="0.4"/>
<text x="361" y="222" font-family="sans-serif" font-size="16" font-weight="bold" fill="#7aaad0">powered by DeepSeek V4</text>
<text x="361" y="248" font-family="sans-serif" font-size="14" font-weight="bold" fill="#90d8ff">&#x1F40B; &#x00A9; 2026 carafife &#x2014; Nseek v1.0 &#x2014; GPL v3</text>
</svg>'''

# ── Logo ciel (splash screen fond sombre) ────────────────────────────────────
svg_ciel = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 330">
<defs>
<linearGradient id="wg" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" stop-color="#90d8ff"/><stop offset="100%" stop-color="#5ab4f0"/></linearGradient>
<linearGradient id="wb" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" stop-color="#c8eeff"/><stop offset="100%" stop-color="#90d8ff"/></linearGradient>
</defs>
<g transform="translate(10,20)">
<path d="M55 95C40 78 22 70 15 80C12 90 22 102 38 106C45 108 52 104 55 95Z" fill="url(#wg)"/>
<path d="M55 105C42 118 28 122 18 116C12 110 18 98 35 96C44 94 52 98 55 105Z" fill="url(#wg)"/>
<path d="M54 100C65 100 80 98 95 96" fill="none" stroke="#2a5a9a" stroke-width="12" stroke-linecap="round"/>
<path d="M88 97C100 80 125 62 162 52C198 42 240 44 272 60C300 74 316 100 316 126C316 152 302 174 278 186C260 196 238 198 218 194C200 190 185 180 176 168Z" fill="url(#wg)"/>
<path d="M102 94C122 80 150 70 182 64C214 58 246 62 268 76C288 90 298 112 296 136C294 158 280 176 260 184C242 190 220 190 204 184C188 178 176 166 168 152C150 128 120 108 102 94Z" fill="url(#wb)" opacity="0.65"/>
<path d="M202 46C209 24 220 10 230 14C226 26 218 38 210 48Z" fill="#2a5a9a"/>
<path d="M148 70C124 60 100 64 88 78C98 88 122 86 142 80Z" fill="#2a5a9a"/>
<path d="M218 194C232 200 248 198 260 190C272 182 280 168 276 154C272 142 260 136 248 138C260 146 266 160 260 172C254 184 238 192 218 194Z" fill="url(#wg)"/>
<path d="M238 182C249 192 262 192 270 186" fill="none" stroke="white" stroke-width="3.5" stroke-linecap="round"/>
<circle cx="258" cy="152" r="7.5" fill="white"/>
<circle cx="259.5" cy="152" r="4.2" fill="#0a1e3a"/>
<circle cx="261" cy="150" r="1.6" fill="white"/>
<path d="M229 46C228 32 226 16 224 4C228 16 230 8 231 0C232 8 234 16 236 4C235 16 233 32 231 46Z" fill="white" opacity="0.95"/>
<path d="M224 42C214 28 202 16 194 10C198 20 196 14 199 9C203 15 208 24 214 36Z" fill="#c8eeff" opacity="0.85"/>
<path d="M236 42C246 28 258 16 266 10C262 20 264 14 261 9C257 15 252 24 246 36Z" fill="#c8eeff" opacity="0.85"/>
</g>
<text x="358" y="158" font-family="sans-serif" font-weight="bold" font-size="88" letter-spacing="-2" fill="#c8eeff">Nseek</text>
<text x="361" y="192" font-family="sans-serif" font-size="17" fill="#90d8ff">client IA natif Linux</text>
<rect x="361" y="200" width="185" height="2" rx="1" fill="#90d8ff" opacity="0.6"/>
<text x="361" y="222" font-family="sans-serif" font-size="16" font-weight="bold" fill="#7aaad0">powered by DeepSeek V4</text>
<text x="361" y="248" font-family="sans-serif" font-size="14" font-weight="bold" fill="#c8eeff">&#x1F40B; &#x00A9; 2026 carafife &#x2014; Nseek v1.0 &#x2014; GPL v3</text>
</svg>'''

assets = os.path.expanduser('~/Programmes/assets')

# Générer logo standard
cairosvg.svg2png(bytestring=svg_standard.encode(),
                 write_to=f'{assets}/nseek-logo.png', output_width=680, output_height=330)
print(f"nseek-logo.png OK ({os.path.getsize(f'{assets}/nseek-logo.png')} bytes)")

# Générer logo ciel (splash fond sombre)
cairosvg.svg2png(bytestring=svg_ciel.encode(),
                 write_to=f'{assets}/nseek-logo-ciel.png', output_width=680, output_height=330)
print(f"nseek-logo-ciel.png OK ({os.path.getsize(f'{assets}/nseek-logo-ciel.png')} bytes)")
