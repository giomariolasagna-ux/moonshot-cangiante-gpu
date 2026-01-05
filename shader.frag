#include <TD/TDCommon.glsl>
uniform sampler2D sTD2DInputs[1];
uniform float uWarp, uChroma, uGrain, uGravity, uPersistence, uBreak;

out vec4 fragColor;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

void main() {
    vec2 uv = TDFragCoordToUV(gl_FragCoord.xy);
    
    // Agency Layer: Se uBreak sale, l'immagine "si ribella" con glitch orizzontali
    if(uBreak > 0.05) {
        float b = hash(vec2(floor(uv.y * (15.0 + uBreak * 40.0)), uTime.x));
        uv.x += (b - 0.5) * 0.12 * uBreak;
    }

    float freq = 3.0 * (1.0 - uGravity * 0.6);
    float n = hash(uv * freq + uTime.x * 0.1);
    vec2 p = uv + (vec2(cos(n*6.28), sin(n*6.28)) * uWarp * 0.15);

    vec4 color = texture(sTD2DInputs[0], p);
    
    // Inversione cromatica drammatica al picco della rottura
    if(uBreak > 0.85) color.rgb = 1.0 - color.rgb;

    color.rgb += (hash(uv + uTime.x) - 0.5) * uGrain * 0.15;
    fragColor = TDOutputSwizzle(color);
}
