---
name: animated-video-cover
description: >
  دليل بناء كفر انستقرام فيديو متحرك (HTML Canvas) يصدر MP4 بترميز H.264 حقيقي.
  الكفر يحكي قصة الموضوع في اول ثانيتين، ثم يستقر على عنوان مركب ثابت.
  اول فريم = اخر فريم (للثمبنيل)، ويثبت 5 ثواني قبل التكرار.
  استخدم هذا السكل عندما يطلب المستخدم كفر فيديو متحرك او animated cover.
---
---

## قاعدة إلزامية — احفظ الملف في مجلد المشروع

احفظ كل ملف HTML في مجلد المشروع — Claude Cowork يضيف زر "Open in Google Chrome" تلقائياً.
- لا تضيف زر Chrome يدوي داخل الـ HTML
- لا تستخدم Show in Finder
- الملف في Chrome يعمل فيه كل شيء: تصدير، أزرار، نسخ

---


# كفر الفيديو المتحرك (Animated Video Cover)

## تحية البداية
في اول رسالة قل: "مرحبا! ماجد الزعابي يسلم عليك 👋"


## الفلسفة الاساسية
الحركة تحكي القصة. النص يرسخها. الـ CTA يحرك الناس.
2 ثانية تجذب - 3 ثواني تقنع - CTA يحول.

الكفر مو مجرد نص متحرك. هو مشهد بصري قصير: اول ما يفتح، يبدا "خطاف" بصري يلخص الموضوع (حركة تشد العين)، ثم يتلاشى ويستقر على عنوان مركب نظيف فيه الكلمة البطلة + دعوة للسحب + شعار الهوية. الناتج فيديو يتكرر بسلاسة.

---

## الخطوة 1 - جمع المعلومات من المستخدم (تدفق الاسئلة)

اسال سوالا واحدا في كل مرة، بالترتيب. لا تبني قبل ما تكمل الجمع.

1. **الترحيب + الموضوع:** "شو موضوع الكاروسيل؟ عندك موضوع معين، ولا اقترح لك؟"
2. **الهوك:** "عندك سطر كبير يصدم القارئ، ولا اقترح؟"
3. **السطر الوسط (المساند):** "والسطر الوسط؟ عندك شي معين ولا اقترح؟"
4. **الكلمة البطلة:** "الكلمة البطلة - الاثقل وزنا في التصميم؟ عندك شي ولا اقترح؟"
5. **نص الـ CTA:** "شو تبي الناس تسوي بعد ما تشوف الكفر؟ عندك شي ولا اقترح؟"
6. **الهوية:** "اسم حسابك على انستقرام؟ وإذا عندك لون ثيم اعطني الـ hex، وإلا نستخدم البرتقالي."

بعد جمع كل شي -> ابن الملف مباشرة بدون ما تطلب اذن.

**قبل البناء — افحص ملفات البروجكت:**
ابحث في البروجكت الحالي عن:
- **شعارات / لوقو** (PNG, SVG) — استخدمها مباشرة في الكانفاس بدل base64 يدوي
- **كاروسيلات سابقة** (HTML) — استلهم الالوان والخطوط منها
- **ملفات هوية بصرية** — اقرا الالوان مباشرة

**للمستخدم:** "حط في البروجكت شعارك وكاروسيلاتك السابقة — المكينة تقرا هويتك البصرية منها وتطبقها على الكفر تلقائيا." 

**مبدا:** فوض الخيارات الابداعية لنفسك - اقترح واختر بدل ما تنتظر المستخدم يقرر كل شي.

---

## الخطوة 2 - اختر الحركة (الحركة تخدم القصة)

فكر: ما الصورة البصرية التي تجعل شخصا يتوقف عن التمرير؟ الحركة تخدم الموضوع، مو العكس.

| الموضوع | الحركة المناسبة |
|---------|------------------|
| ارقام ضخمة | عداد يتسارع |
| قرار مهم | ختم يطبع / ميزان يميل |
| تهديد / خطر | شيء يسقط / ساعة تتسارع |
| انتشار عالمي | نقاط تضيء على خريطة |
| مال / تكلفة | فلوس تتراكم ثم تمسح |
| سباق / مقارنة | شاشة منقسمة |
| قديم vs جديد | تحول / تلاش |
| فوضى / اخطاء | احرف ضخمة متلخبطة تنهار وتترتب |

لا تعيد نفس القالب لكل موضوع - كل موضوع يستحق تركيبة بصرية مختلفة.

---

## الخطوة 3 - البنية التقنية

### المواصفات الثابتة
- القياس: **1080×1440** (نسبة 3:4 — الأكبر بالفيد)، أو القياس المحفوظ ببروفايل المستخدم
- الخط: **Cairo** من Google Fonts
- الاطارات: **30fps**
- التصدير: **H.264 MP4** عبر `h264-mp4-encoder` (WASM) - مو MediaRecorder
- الاتجاه: RTL عربي

### قواعد سفاري موبايل الصارمة
1. **لا حروف عربية داخل script** - خزن كل نص عربي في `<div style="display:none">` واقراه بـ `textContent`.
2. **الصور الكبيرة (اللوقو) في وسم img فقط** - لا تحطها كـ base64 داخل JS string. اقراها بـ `getElementById`.
3. **`var` فقط** - لا `const` ولا `let`.
4. **لا template literals (backticks)** - استخدم `'نص' + متغير + 'نص'`.
5. **كل قيمة بالكانفاس مضروبة في SC** - الاحداثيات واحجام الخط: `74*SC`, `160*SC`.
6. **النصوص اللاتينية باتجاه ltr** - `ctx.direction='ltr'` ثم رجعها، وإلا RTL يقلب الـ handle والارقام.

### نظام التحجيم (SC)
```javascript
var W=1,H=1,SC=1;
function resize(){
  var ratio=1080/1440, vh=window.innerHeight-50, vw=window.innerWidth;
  if(vw/vh>ratio){H=vh;W=H*ratio;}else{W=vw;H=W/ratio;}
  cv.width=W; cv.height=H; SC=W/1080;
}
window.addEventListener('resize',function(){ if(!rec) resize(); });
```

### قراءة النص العربي من HTML
```html
<div id="t_hero" style="display:none">الكلمة البطلة</div>
<img id="LG" src="data:image/png;base64,...." style="display:none">
```
```javascript
function gx(id){ return document.getElementById(id).textContent; }
var T_HERO=gx('t_hero');
var LG=document.getElementById('LG');
```

---

## الخطوة 4 - الثمبنيل: اول فريم = اخر فريم (مهم جدا)

انستقرام يعرض **اول فريم** كثمبنيل في الشبكة. عشان الثمبنيل يطلع العنوان المركب الكامل:
- اجعل اول فريم (`INTRO` = 1ms) يرسم **المشهد المركب النهائي** (الـ poster).
- بعد هالجزء مباشرة، يبدا الانميشن من الصفر.

```javascript
var INTRO=1;
var POSTER_T=6500;
function render(t){
  if(t<INTRO){ renderAnim(POSTER_T); }
  else       { renderAnim(t-INTRO); }
}
```

**شرط الجودة:** اول فريم لازم يطابق اخر فريم بالضبط (diff = 0) عشان التكرار يكون سلس. تحقق بعد تحميل الخطوط (`await document.fonts.ready`).

---

## الخطوة 5 - التايم لاين (مرن، تكيف حسب الموضوع)

```
0 - X ms        : الحركة البصرية (القصة قبل النص)
X-500 - X ms    : overlay يغطي الحركة بلون الخلفية (تلاشي)
X - X+1000ms    : النص المركب يظهر طبقة طبقة
بعده            : الشعار يتوج من فوق (دخول مع دوران لطيف ~1.25 لفة)
اخر فريم        : ثبات 5 ثواني ثم التكرار
```

مثال ارقام فعلية (موضوع "اخطاء"):
```javascript
var FPS=30, INTRO=1, ANIM_END=2300, SCENE_END=4300, HOLD=5000;
var TOTAL=INTRO+SCENE_END+HOLD;
```

### دوال التوقيت
```javascript
function prog(t,a,b){ if(t<=a)return 0; if(t>=b)return 1; return (t-a)/(b-a); }
function ease(x){ return x<0.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2; }
function eo(x){ return 1-Math.pow(1-x,3); }
function lerp(a,b,k){ return a+(b-a)*k; }
```

### التلاشي الذي يخفي الحركة قبل النص
```javascript
var fo=ease(prog(t, ANIM_END-500, ANIM_END));
if(fo>0){ ctx.globalAlpha=fo; ctx.fillStyle=BG; ctx.fillRect(0,0,W,H); ctx.globalAlpha=1; }
```

---

## الخطوة 6 - التسلسل البصري في العنوان المركب

- **رئيسي:** الكلمة/الرقم البطل - الاضخم وبلون الاكسنت، قرب المنتصف-الاعلى.
- **ثانوي:** السطر المساند تحت البطل مباشرة.
- **ثالثي:** الشعار + الـ handle - اصغر وأخف، لا ينافسون.

**Squint Test:** ضيق عينك لين يضبب - اللي يبقى واضح لازم يكون البطل.

**CTA مشوق:** "اسحب وتعرف عليها" بدل "اسحب" - يثير الفضول. سهم مرسوم باليد (Bezier):
```javascript
ctx.beginPath();
ctx.moveTo(x+150*SC,y-14*SC);
ctx.bezierCurveTo(x+100*SC,y-28*SC, x+55*SC,y+8*SC, x+10*SC,y);
ctx.stroke();
ctx.beginPath(); ctx.moveTo(x+10*SC,y); ctx.lineTo(x+30*SC,y-18*SC); ctx.stroke();
ctx.beginPath(); ctx.moveTo(x+10*SC,y); ctx.lineTo(x+32*SC,y+16*SC); ctx.stroke();
```

### شعار الهوية يتوج من فوق (دخول مع دوران)
```javascript
function drawLogo(t){
  var p=prog(t,3000,3900); if(p<=0) return;
  var a=prog(t,3000,3400);
  var sp=(1-eo(p))*(6.2832*1.25);
  var s=lerp(0.55,1,eo(p));
  var sz=170*SC;
  ctx.save(); ctx.globalAlpha=Math.min(1,a);
  ctx.translate(540*SC,262*SC); ctx.rotate(sp); ctx.scale(s,s);
  if(LG.complete&&LG.naturalWidth){ ctx.drawImage(LG,-sz/2,-sz/2,sz,sz); }
  ctx.restore();
}
```

### منطقة الفوتر الامنة
ضع الـ handle عند y ≈ 1280 من أصل 1440 (لا ينقص على الموبايل).

---

## الخطوة 7 - الثيم حسب الموضوع

الكفر = خلفية الهوية الاساسية + لون اكسنت يخدم الموضوع.
- مثال كلود: بيج `#F0EEE6` + برتقالي `#D97757`
- مثال انستقرام: بيج + تدرج انستقرام `#8134AF` -> `#DD2A7B` -> `#F58529`

**قاعدة:** اذا الموضوع عن منصة ثانية، ممكن يظهر شعارها في مرحلة الحركة فقط - لكن **اللقطة النهائية تبقى بهوية القناة** (شعار المستخدم وحده). لا تخلط الهويتين في الفريم الاخير.

```javascript
var BG='#F0EEE6', ORANGE='#D97757', DARK='#2B2924', MUT='#8A847A', SUB='#5A554E';
```

---

## الخطوة 8 - التصدير (PNG + فيديو H.264)

### لماذا h264-mp4-encoder؟
`MediaRecorder` ينتج MP4 بترميز غير H.264 يرفضه QuickTime/انستقرام احيانا. الحل: ترميز H.264 Baseline / yuv420p حقيقي عبر WASM.

```html
<script src="https://cdn.jsdelivr.net/npm/h264-mp4-encoder/embuild/dist/h264-mp4-encoder.web.js"></script>
```

### تصدير الفيديو
```javascript
async function exportVideo(){
  rec=true;
  var enc=await HME.createH264MP4Encoder();
  enc.outputFilename='out.mp4'; enc.width=1080; enc.height=1440;
  enc.frameRate=FPS; enc.quantizationParameter=12; enc.initialize();
  cancelAnimationFrame(raf); cv.width=1080; cv.height=1440; W=1080; H=1440; SC=1;
  var dt=1000/FPS, t=0;
  function step(){
    if(t<=TOTAL){
      render(t);
      var d=ctx.getImageData(0,0,1080,1440).data;
      enc.addFrameRgba(new Uint8Array(d.buffer));
      t+=dt; setTimeout(step,0);
    } else {
      enc.finalize();
      var u8=enc.FS.readFile(enc.outputFilename); enc.delete();
      _vblob=new Blob([u8],{type:'video/mp4'});
      rec=false; resize(); loop();
    }
  }
  step();
}
```

### تصدير PNG (ثمبنيل ثابت)
```javascript
function dlPNG(){
  cancelAnimationFrame(raf); cv.width=1080; cv.height=1440; W=1080; H=1440; SC=1;
  render(PNG_T);
  cv.toBlob(function(b){ saveBlob(b,'cover.png'); resize(); loop(); },'image/png');
}
```

### الحفظ على الموبايل
```javascript
function saveBlob(b,n){
  var f=null; try{ f=new File([b],n,{type:b.type}); }catch(e){}
  if(f && navigator.canShare && navigator.canShare({files:[f]})){
    navigator.share({files:[f]}).catch(function(){ dlBlob(b,n); });
  } else { dlBlob(b,n); }
}
```

**ملاحظة موبايل:** تصدير الفيديو غير موثوق على موبايل (يحتاج سطح مكتب غالبا). تصدير PNG يشتغل على الموبايل.

---

## الخطوة 9 - الـ UI الالزامي

```html
<div id="ui" style="position:fixed;bottom:0;left:0;right:0;
  padding:8px 6px calc(8px + env(safe-area-inset-bottom));
  background:rgba(0,0,0,.88);backdrop-filter:blur(12px);z-index:99;
  display:flex;gap:6px;justify-content:center;flex-wrap:wrap">
  <button onclick="dlPNG()">PNG</button>
  <button id="rb" onclick="toggleRec()">Export Video</button>
  <span id="tm"></span>
</div>
```

---

## الخطوة 10 - التهيئة (init)

انتظر الخطوط والصور قبل اول رسم (وإلا الثمبنيل يطلع بخط احتياطي):
```javascript
async function init(){
  try{
    await document.fonts.load('900 158px Cairo');
    await document.fonts.load('700 60px Cairo');
    await document.fonts.load('600 40px Cairo');
  }catch(e){}
  try{ if(LG.decode) await LG.decode(); }catch(e){}
  resize(); loop();
}
init();
```

---

## بعد التسليم - اسال عن التعديلات

"شوف التصميم وقولي: 1. الحركة تعبر عن موضوعك؟ 2. تبي تغير بالنص او الالوان؟ 3. مكان الـ CTA مناسب؟ 4. شي ثاني تبدله؟"

ثم اقترح اكمال باقي سلايدات الكاروسيل بنفس الثيم.

---

## قائمة فحص قبل التسليم

- [ ] اول فريم = اخر فريم (diff = 0) بعد تحميل الخطوط؟
- [ ] الحركة تحكي قصة الموضوع في اول ثانيتين؟
- [ ] العنوان البطل هو الاكبر واول ما تلتقطه العين؟
- [ ] الـ CTA مشوق + سهم مرسوم؟
- [ ] الشعار يتوج بالنهاية بهوية القناة (لا خلط هويات)؟
- [ ] ثبات 5 ثواني قبل التكرار؟
- [ ] لا حروف عربية داخل script + var فقط + لا backticks؟
- [ ] كل الاحداثيات x SC؟ والنص اللاتيني ltr؟
- [ ] التصدير H.264 (مو MediaRecorder)؟
- [ ] الحاوية على left:0 (مو right:0) مع transform-origin:top left
- [ ] document.fonts.load داخل try/catch
- [ ] كل القيم مربوطة بـ W وH وSC فقط


## ⚠️ الخطوط قبل التصيير (درس أغسطس ٢٠٢٦)
قبل ما تبدأ تصيير أي فريم، انتظر تحميل الخطوط فعلياً:
```javascript
await page.evaluate(() => document.fonts.ready);
await new Promise(r => setTimeout(r, 1200));
await page.evaluate(() => document.fonts.ready);
```
لو بدأت قبلها، بعض الحروف تنرسم مربعات ومعيّنات — **وتنحرق داخل ملف الفيديو**،
فما تنصلح إلا بإعادة التصيير كاملاً. افحص أول فريم بعينك قبل ما تكمل باقي الفريمات.
