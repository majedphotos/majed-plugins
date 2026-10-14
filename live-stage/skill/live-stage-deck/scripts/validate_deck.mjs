#!/usr/bin/env node
// مدقق deck.json: يتأكد إن كل عبارة تفتح مشهدها، وإن كلام المتحدث العادي ما يفتح مشهد بالغلط.
// يستخدم نفس كود المطابقة اللي في صفحة العرض (بين PARSER_START و PARSER_END)، فالنتيجة هي نفس اللي بيصير على المسرح.
// الاستخدام: node validate_deck.mjs <deck.json> [live-stage.html]
import fs from 'node:fs';
import path from 'node:path';

const deckPath = process.argv[2];
if (!deckPath) { console.error('الاستخدام: node validate_deck.mjs <deck.json> [live-stage.html]'); process.exit(2); }
// صفحة العرض: المسار الثاني، أو $LIVE_STAGE_DIR، أو جنب deck.json، أو المجلد الحالي، أو جذر المشروع لو السكل داخل skill/
const here = path.dirname(new URL(import.meta.url).pathname);
const pagePath = [
  process.argv[3],
  process.env.LIVE_STAGE_DIR && path.join(process.env.LIVE_STAGE_DIR, 'live-stage.html'),
  path.join(path.dirname(path.resolve(deckPath)), 'live-stage.html'),
  path.join(path.dirname(path.resolve(deckPath)), '..', 'live-stage.html'),
  path.resolve('live-stage.html'),
  path.join(here, '..', '..', '..', 'live-stage.html'),
].find((p) => p && fs.existsSync(p));
if (!pagePath) { console.error('ما لقيت live-stage.html. مرّر مساره: node validate_deck.mjs <deck.json> <live-stage.html> أو حط LIVE_STAGE_DIR'); process.exit(2); }

const html = fs.readFileSync(pagePath, 'utf8');
const a = html.indexOf('/*PARSER_START*/'), b = html.indexOf('/*PARSER_END*/');
if (a < 0 || b < 0) { console.error('ما لقيت كود المطابقة في الصفحة: ' + pagePath); process.exit(2); }
const P = new Function(html.slice(a, b) + '\n;return {tokenize, matchSceneIn, sceneSay};')();

let deck;
try { deck = JSON.parse(fs.readFileSync(deckPath, 'utf8')); }
catch (e) { console.error('❌ الملف مو JSON صحيح: ' + e.message); process.exit(1); }

const WINDOW = 3;
const errors = [], warns = [];
const err = (m) => errors.push(m), warn = (m) => warns.push(m);
const name = (i) => `المشهد ${i + 1}${deck.scenes[i] && deck.scenes[i].id ? ' (' + deck.scenes[i].id + ')' : ''}`;
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const str = (v) => typeof v === 'string' && v.trim().length > 0;

// ---------- الشكل ----------
if (!Array.isArray(deck.scenes) || !deck.scenes.length) { console.error('❌ لازم يكون فيه "scenes" وفيها مشهد واحد على الأقل'); process.exit(1); }
if (deck.context !== undefined && typeof deck.context !== 'string') err('"context" لازم يكون نص');
if (typeof deck.context === 'string' && deck.context.length > 4000) warn(`"context" طويل (${deck.context.length} حرف)، الصفحة تاخذ أول ٤٠٠٠ بس`);

const ids = new Set();
const NEEDS_SOURCE = new Set(['counter', 'bars']);
function checkShow(i, sh) {
  const n = name(i);
  if (!sh || typeof sh !== 'object') return err(`${n}: "show" فاضي`);
  switch (sh.t) {
    case 'title': if (!str(sh.text)) err(`${n}: title يحتاج "text"`); break;
    case 'keyword': if (!str(sh.text)) err(`${n}: keyword يحتاج "text"`); break;
    case 'counter': if (!isNum(sh.value)) err(`${n}: counter يحتاج "value" رقم`); break;
    case 'list': {
      const k = Array.isArray(sh.items) ? sh.items.length : sh.n;
      if (!(k >= 2 && k <= 10)) err(`${n}: list يحتاج من ٢ إلى ١٠ عناصر`);
      if (sh.reveal && (!Array.isArray(sh.items) || sh.items.some((x) => !str(x)))) err(`${n}: list مع reveal لازم كل عناصره مكتوبة`);
      break;
    }
    case 'cards':
      if (!Array.isArray(sh.cards) || !sh.cards.length || sh.cards.length > 12) err(`${n}: cards يحتاج من ١ إلى ١٢ بطاقة`);
      else sh.cards.forEach((c, k) => { if (!str(c && c.title)) err(`${n}: البطاقة ${k + 1} بدون "title"`); if (c && c.color && !/^#[0-9a-f]{6}$/i.test(c.color)) err(`${n}: لون البطاقة ${k + 1} لازم يكون #RRGGBB`); });
      break;
    case 'bars':
      if (!Array.isArray(sh.items) || sh.items.length < 2 || sh.items.length > 6) err(`${n}: bars يحتاج من ٢ إلى ٦ أعمدة`);
      else sh.items.forEach((it, k) => { if (!isNum(it && it.value) || it.value < 0) err(`${n}: العمود ${k + 1} يحتاج "value" رقم موجب`); });
      break;
    case 'timeline':
      if (!Array.isArray(sh.items) || sh.items.length < 2 || sh.items.length > 6) err(`${n}: timeline يحتاج من ٢ إلى ٦ محطات`);
      else sh.items.forEach((it, k) => { if (!str(it && it.label)) err(`${n}: المحطة ${k + 1} بدون "label"`); });
      break;
    case 'poll':
      if (!str(sh.question)) err(`${n}: poll يحتاج "question"`);
      if (!Array.isArray(sh.options) || sh.options.length < 2 || sh.options.length > 6) err(`${n}: poll يحتاج من ٢ إلى ٦ خيارات`);
      break;
    case 'image':
      if (!/^assets\/[\w\-./]+$/.test(sh.src || '') || sh.src.includes('..')) err(`${n}: image لازم "src" يبدأ بـ assets/`);
      else if (!fs.existsSync(path.join(path.dirname(path.resolve(deckPath)), sh.src))) err(`${n}: الصورة ${sh.src} مو موجودة جنب deck.json`);
      break;
    case 'sketch':
      if (!Array.isArray(sh.shapes) || !sh.shapes.length || sh.shapes.length > 30) err(`${n}: sketch يحتاج من ١ إلى ٣٠ شكل`);
      break;
    case 'map': if (!['africa', 'kenya'].includes(sh.region)) err(`${n}: map يدعم africa أو kenya بس`); break;
    default: err(`${n}: نوع رسم مو معروف "${sh.t}"`);
  }
}

deck.scenes.forEach((sc, i) => {
  const n = name(i);
  if (!str(sc.id)) err(`المشهد ${i + 1}: بدون "id"`);
  else if (ids.has(sc.id)) err(`${n}: الـ id مكرر`);
  else ids.add(sc.id);
  if (!Array.isArray(sc.say) || !sc.say.length) err(`${n}: لازم يكون فيه "say" بعبارة وحدة على الأقل`);
  (sc.say || []).forEach((p) => {
    if (!P.tokenize(p).length) err(`${n}: العبارة "${p}" فاضية بعد التنظيف`);
    // التعرف على الكلام بالعربي يكتب الأسماء الإنقليزية بالعربي غالباً (iPhone → ايفون)
    if (/[a-z]/i.test(p) && !(sc.say || []).some((q) => q !== p && !/[a-z]/i.test(q))) warn(`${n}: "${p}" فيها حروف إنقليزية. ضيف معها صيغة عربية (مثل "ايفون") لأن التعرف على الكلام غالباً يكتبها بالعربي`);
  });
  const shows = Array.isArray(sc.show) ? sc.show : [sc.show];
  shows.forEach((sh) => checkShow(i, sh));
  if (shows.some((sh) => sh && NEEDS_SOURCE.has(sh.t)) && !str(sc.source)) warn(`${n}: فيه أرقام بدون "source". تأكد إن الرقم من المستخدم أو من مصدر موثوق`);
  if (!(sc.say || []).some((p) => P.tokenize(p).length >= 2)) warn(`${n}: كل عباراته كلمة وحدة. ضيف عبارة من كلمتين عشان تقدر تقفز له لو تخطيت مشهد`);
});

if (errors.length) report();

// ---------- محاكاة العرض ----------
const scenes = deck.scenes;
scenes.forEach((sc) => { sc._say = P.sceneSay(sc); });

// ١) كل عبارة، لما تنقال وأنت في المشهد اللي قبله، لازم تفتح مشهدها بالضبط
scenes.forEach((sc, i) => {
  (sc.say || []).forEach((p) => {
    const got = P.matchSceneIn(scenes, i - 1, `يا جماعة ${p} الحين`, WINDOW);
    if (got !== i) err(`${name(i)}: العبارة "${p}" ${got < 0 ? 'ما تفتح أي مشهد' : 'تفتح ' + name(got) + ' بدال'}`);
  });
});

// ٢) كلام المتحدث داخل كل مشهد (talk) ما لازم يفتح أي مشهد
scenes.forEach((sc, i) => {
  (sc.talk || []).forEach((line) => {
    const got = P.matchSceneIn(scenes, i, line, WINDOW);
    if (got >= 0) err(`${name(i)}: الجملة "${line}" تفتح ${name(got)} بالغلط. غيّر عبارات ${name(got)} أو صياغة الجملة`);
  });
});

// ٣) لو كرر عبارة المشهد وهو فيه، ما لازم يقفز للي بعده
scenes.forEach((sc, i) => {
  (sc.say || []).forEach((p) => {
    const got = P.matchSceneIn(scenes, i, p, WINDOW);
    if (got >= 0) warn(`${name(i)}: لو كررت "${p}" وأنت في المشهد، بيفتح ${name(got)}. العبارات متشابهة`);
  });
});

// ٤) عبارة مشهد سابق قريب، لو انقالت مرة ثانية، ما لازم تقفز قدام
scenes.forEach((sc, i) => {
  for (let c = i + 1; c <= Math.min(scenes.length - 1, i + WINDOW); c++) {
    (sc.say || []).forEach((p) => {
      const got = P.matchSceneIn(scenes, c, p, WINDOW);
      if (got >= 0) warn(`لو رجعت قلت "${p}" (${name(i)}) وأنت في ${name(c)}، بيفتح ${name(got)}`);
    });
  }
});

report();

function report() {
  const total = deck.scenes.length;
  console.log(`فحص ${deckPath}: ${total} مشهد`);
  if (errors.length) { console.log(`\n❌ أخطاء (${errors.length}):`); errors.forEach((e) => console.log('  - ' + e)); }
  if (warns.length) { console.log(`\n⚠️ تنبيهات (${warns.length}):`); warns.forEach((w) => console.log('  - ' + w)); }
  if (!errors.length) console.log(`\n✅ كل العبارات تفتح مشاهدها، وجمل الكلام ما تفتح شي بالغلط`);
  process.exit(errors.length ? 1 : 0);
}
