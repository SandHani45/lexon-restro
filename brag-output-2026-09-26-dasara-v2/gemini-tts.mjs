// Usage: node gemini-tts.mjs <out.wav> <text> — reads GOOGLE_API_KEY from project .env (never printed)
import fs from "fs";
const env = fs.readFileSync(new URL("../.env", import.meta.url), "utf8");
const key = (env.match(/^GOOGLE_API_KEY\s*=\s*"?([^"\r\n]+)"?/m) || [])[1];
const [out, text] = process.argv.slice(2);
const model = process.env.TTS_MODEL || "gemini-2.5-flash-preview-tts";
const style = "Speak in natural, native Telugu as a warm, friendly young woman from Hyderabad talking to a restaurant owner she knows. Conversational, smiling, expressive, natural pauses, not robotic, not like a news reader. Say exactly this: ";
const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "x-goog-api-key": key },
  body: JSON.stringify({
    contents: [{ parts: [{ text: style + text }] }],
    generationConfig: { responseModalities: ["AUDIO"], speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: process.env.TTS_VOICE || "Kore" } } } },
  }),
});
const j = await res.json();
const b64 = j?.candidates?.[0]?.content?.parts?.[0]?.inlineData?.data;
if (!b64) { console.error("TTS failed:", res.status, JSON.stringify(j).slice(0, 400)); process.exit(1); }
const pcm = Buffer.from(b64, "base64");
const h = Buffer.alloc(44);
h.write("RIFF", 0); h.writeUInt32LE(36 + pcm.length, 4); h.write("WAVE", 8); h.write("fmt ", 12);
h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(24000, 24);
h.writeUInt32LE(48000, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(pcm.length, 40);
fs.writeFileSync(out, Buffer.concat([h, pcm]));
console.log(out, (pcm.length / 48000).toFixed(2) + "s");
