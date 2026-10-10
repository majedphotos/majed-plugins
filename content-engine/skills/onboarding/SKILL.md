---
name: onboarding
description: يجمع هوية صانع المحتوى ويحفظها في .auto-memory/creator-profile.md — يُشغَّل تلقائياً في أول استخدام أو عند قول "سجل بياناتي"، "عرّف نفسك"، "احفظ معلوماتي"، "أنا صانع محتوى". يعرض استبانة تفاعلية داخل الشات مباشرة. ALWAYS use this skill at the very start before any other skill if no creator-profile.md exists.
---

# Onboarding — مصنع المحتوى

## تحية البداية
في أول رسالة للمستخدم قل:
"مرحباً! ماجد الزعابي يسلم عليك 👋 — أنا مكينة المحتوى، جاهز أساعدك تبني محتوى انستقرام احترافي بهويتك."

## الهدف
جمع هوية صانع المحتوى عبر استبانة تفاعلية تظهر داخل الشات مباشرة، ثم حفظها في `.auto-memory/creator-profile.md`.

## الخطوات

### 1. تحقق من وجود بروفايل
ابحث في فولدر المشروع عن `.auto-memory/creator-profile.md`:
- **إن وجد:** اقرأه واسأل المستخدم إن أراد التعديل عليه
- **إن لم يوجد:** انتقل لخطوة 2

### 2. اسأل عن الملفات الموجودة (سؤال واحد)
"عندك ملفات هوية بصرية (شعار، كاروسيلات سابقة، ألوان ثيم) تبي أقرأها، ولا نبدأ من صفر؟"

**إذا قال عنده ملفات:** ابحث في فولدر المشروع عن صور وملفات HTML، استخرج منها الألوان والأسلوب، اعرض ما وجدت واطلب تأكيده، ثم انتقل لخطوة 4.
**إذا قال من صفر:** انتقل لخطوة 3.

### 3. ابنِ الاستبانة كـ artifact داخل الشات

**مهم:** اعرض الاستبانة كاملة دفعة واحدة كـ artifact — لا تسأل سؤالاً سؤالاً ولا تكتب مقدمة. استخدم `create_artifact` مع الـ HTML أدناه مباشرة:

```html
<h2 class="sr-only">استبانة هوية صانع المحتوى</h2>

<style>
.ob-wrap { padding: 1rem 0; }
.ob-section { background: var(--color-background-secondary); border: 0.5px solid var(--color-border-tertiary); border-radius: var(--border-radius-lg); padding: 1rem 1.25rem; margin-bottom: 12px; }
.ob-label { font-size: 14px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 3px; }
.ob-hint { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 10px; }
.chips { display: flex; flex-wrap: wrap; gap: 7px; direction: rtl; }
.chip { background: var(--color-background-primary); border: 0.5px solid var(--color-border-secondary); border-radius: 20px; padding: 6px 14px; font-size: 13px; cursor: pointer; color: var(--color-text-secondary); transition: all 0.15s; user-select: none; font-family: inherit; }
.chip:hover { border-color: var(--color-border-primary); color: var(--color-text-primary); }
.chip.on { background: #D97757; border-color: #D97757; color: #fff; font-weight: 500; }
.chip.disabled { opacity: 0.38; cursor: default; pointer-events: none; }
.ob-other { margin-top: 8px; display: none; }
.ob-other.show { display: block; }
.ob-btn { width: 100%; background: #D97757; color: #fff; border: none; border-radius: var(--border-radius-md); padding: 13px; font-size: 15px; font-weight: 500; cursor: pointer; font-family: inherit; margin-top: 4px; transition: opacity 0.15s; }
.ob-btn:hover { opacity: 0.88; }
</style>

<div class="ob-wrap" dir="rtl">

  <div class="ob-section">
    <div class="ob-label">اسم حسابك على انستقرام</div>
    <div class="ob-hint">مثال: @majed_photos</div>
    <input type="text" id="ob-handle" placeholder="@username" style="width:100%; direction:rtl; text-align:right;">
  </div>

  <div class="ob-section">
    <div class="ob-label">نيشك</div>
    <div class="ob-hint">اختر حتى اثنين</div>
    <div class="chips" id="g-niche">
      <span class="chip" data-g="niche" data-max="2">تقنية وذكاء اصطناعي</span>
      <span class="chip" data-g="niche" data-max="2">استثمار ومال</span>
      <span class="chip" data-g="niche" data-max="2">تطوير ذات</span>
      <span class="chip" data-g="niche" data-max="2">ريادة أعمال</span>
      <span class="chip" data-g="niche" data-max="2">رياضة ولياقة</span>
      <span class="chip" data-g="niche" data-max="2">طبخ وأكل</span>
      <span class="chip" data-g="niche" data-max="2">سفر وسياحة</span>
      <span class="chip" data-g="niche" data-max="2">تعليم</span>
      <span class="chip" data-g="niche" data-max="2">ترفيه</span>
      <span class="chip ob-other-trigger" data-g="niche" data-max="2">أخرى</span>
    </div>
    <div class="ob-other" id="other-niche"><input type="text" placeholder="اكتب نيشك" style="width:100%; direction:rtl; text-align:right;"></div>
  </div>

  <div class="ob-section">
    <div class="ob-label">جمهورك</div>
    <div class="ob-hint">اختر كل ما ينطبق</div>
    <div class="chips" id="g-audience">
      <span class="chip" data-g="audience">شباب 18-24</span>
      <span class="chip" data-g="audience">بالغون 25-35</span>
      <span class="chip" data-g="audience">مهنيون وموظفون</span>
      <span class="chip" data-g="audience">رجال أعمال</span>
      <span class="chip" data-g="audience">طلاب</span>
      <span class="chip" data-g="audience">عائلات</span>
    </div>
  </div>

  <div class="ob-section">
    <div class="ob-label">لهجتك</div>
    <div class="ob-hint">اختر واحدة</div>
    <div class="chips" id="g-dialect">
      <span class="chip" data-g="dialect" data-max="1">سعودية</span>
      <span class="chip" data-g="dialect" data-max="1">كويتية</span>
      <span class="chip" data-g="dialect" data-max="1">إماراتية</span>
      <span class="chip" data-g="dialect" data-max="1">مصرية</span>
      <span class="chip" data-g="dialect" data-max="1">خليجية عامة</span>
      <span class="chip" data-g="dialect" data-max="1">فصحى مبسطة</span>
      <span class="chip ob-other-trigger" data-g="dialect" data-max="1">أخرى</span>
    </div>
    <div class="ob-other" id="other-dialect"><input type="text" placeholder="اكتب لهجتك" style="width:100%; direction:rtl; text-align:right;"></div>
  </div>

  <div class="ob-section">
    <div class="ob-label">نبرة محتواك</div>
    <div class="ob-hint">اختر حتى اثنين</div>
    <div class="chips" id="g-tone">
      <span class="chip" data-g="tone" data-max="2">رسمي وموضوعي</span>
      <span class="chip" data-g="tone" data-max="2">ودّي وقريب</span>
      <span class="chip" data-g="tone" data-max="2">جريء ومباشر</span>
      <span class="chip" data-g="tone" data-max="2">تعليمي وشارح</span>
      <span class="chip" data-g="tone" data-max="2">ساخر وخفيف</span>
    </div>
  </div>

  <div class="ob-section">
    <div class="ob-label">منصاتك</div>
    <div class="ob-hint">اختر كل ما ينطبق</div>
    <div class="chips" id="g-platforms">
      <span class="chip" data-g="platforms">انستقرام</span>
      <span class="chip" data-g="platforms">تيك توك</span>
      <span class="chip" data-g="platforms">تويتر / X</span>
      <span class="chip" data-g="platforms">يوتيوب</span>
      <span class="chip" data-g="platforms">لينكدإن</span>
      <span class="chip" data-g="platforms">سناب شات</span>
    </div>
  </div>

  <div class="ob-section">
    <div class="ob-label">ثيم ألوانك</div>
    <div class="ob-hint">اختر ستايل جاهز أو اكتب ألوانك — عندك شعار أو هوية؟ حطها في فولدر المشروع وأنا أستخرج الألوان منها تلقائياً</div>
    <div class="chips" id="g-colors">
      <span class="chip" data-g="colors" data-max="1">ستايل Claude — بيج وبرتقالي</span>
      <span class="chip" data-g="colors" data-max="1">ستايل انستقرام — بنفسجي ووردي</span>
      <span class="chip" data-g="colors" data-max="1">داكن ذهبي</span>
      <span class="chip" data-g="colors" data-max="1">أبيض نظيف</span>
      <span class="chip" data-g="colors" data-max="1">أزرق مؤسسي</span>
      <span class="chip ob-other-trigger" data-g="colors" data-max="1">ألواني الخاصة</span>
    </div>
    <div class="ob-other" id="other-colors"><input type="text" placeholder="مثال: #D97757 خلفية فاتحة #F0EEE6" style="width:100%; direction:ltr; text-align:left;"></div>
  </div>

  <button class="ob-btn" onclick="obSave()">احفظ هويتي ✓</button>
</div>

<script>
document.querySelectorAll('.chip').forEach(function(chip) {
  chip.addEventListener('click', function() {
    var g = chip.dataset.g;
    var max = parseInt(chip.dataset.max) || 99;
    var isOther = chip.classList.contains('ob-other-trigger');
    var group = document.getElementById('g-' + g);
    var otherDiv = document.getElementById('other-' + g);
    if (chip.classList.contains('on')) {
      chip.classList.remove('on');
      if (isOther && otherDiv) otherDiv.classList.remove('show');
      updateDisabled(group, max);
      return;
    }
    var active = group.querySelectorAll('.chip.on').length;
    if (active >= max) return;
    chip.classList.add('on');
    if (isOther && otherDiv) otherDiv.classList.add('show');
    updateDisabled(group, max);
  });
});

function updateDisabled(group, max) {
  var active = group.querySelectorAll('.chip.on').length;
  group.querySelectorAll('.chip').forEach(function(c) {
    if (!c.classList.contains('on')) {
      if (active >= max) c.classList.add('disabled');
      else c.classList.remove('disabled');
    }
  });
}

function getVals(g) {
  var group = document.getElementById('g-' + g);
  var vals = [];
  group.querySelectorAll('.chip.on').forEach(function(c) {
    if (c.classList.contains('ob-other-trigger')) {
      var inp = document.querySelector('#other-' + g + ' input');
      if (inp && inp.value.trim()) vals.push(inp.value.trim());
    } else {
      vals.push(c.textContent.trim());
    }
  });
  return vals.join('، ');
}

function obSave() {
  var handle = document.getElementById('ob-handle').value.trim();
  if (!handle) { alert('اكتب اسم حسابك أولاً'); return; }
  var niche = getVals('niche');
  var dialect = getVals('dialect');
  var tone = getVals('tone');
  if (!niche || !dialect || !tone) { alert('اختر النيش واللهجة والنبرة على الأقل'); return; }
  var msg = 'احفظ هويتي:\nاسم الحساب: ' + handle
    + '\nالنيش: ' + niche
    + '\nالجمهور: ' + (getVals('audience') || 'غير محدد')
    + '\nاللهجة: ' + dialect
    + '\nالنبرة: ' + tone
    + '\nالمنصات: ' + (getVals('platforms') || 'انستقرام')
    + '\nالألوان: ' + (getVals('colors') || 'غير محدد');
  sendPrompt(msg);
}
</script>
```

### 4. احفظ البروفايل
بعد استلام رسالة "احفظ هويتي:" من المستخدم، احفظ البيانات في `.auto-memory/creator-profile.md`:

```markdown
---
name: creator-profile
description: هوية صانع المحتوى — تستخدم في كل الكاروسيلات والداش بوردات
type: user
---

**اسم الحساب:** [الجواب]
**النيش:** [الجواب]
**الجمهور:** [الجواب]
**اللهجة:** [الجواب]
**نبرة المحتوى:** [الجواب]
**المنصات:** [الجواب]
**الألوان:** [الجواب]
**القياس المفضل:** 1080×1440 (الافتراضي — الأكبر بفيد انستقرام؛ يتغيّر لو طلب المستخدم 1080×1350)
```

### 5. بعد الحفظ — اعرض القائمة
قل للمستخدم:

"تم حفظ هويتك ✅ — من الحين كل كاروسيل وداش بورد راح يكون بألوانك وأسلوبك تلقائياً.

شو تبي نبدأ فيه؟
- **جيب أخبار** — أشوف آخر الأخبار في مجالك وتختار منها
- **اعمل كاروسيل** — حدد الموضوع وأبنيه لك مباشرة
- **كفر فيديو متحرك** — أصمم كفر أول سلايد فيديو يشد الانتباه
- **🛍️ إعلان منتج** — أرسل لي رابط أي منتج وأسحب صوره الرسمية وأبني لك إعلان 10 شرائح كامل
- **👔 فحص جودة** — قبل ما تنشر أي كاروسيل، أشغّل مدير الجودة يفحصه بالرؤية مقابل قيودك (بدون أي نشر)"

### 6. مثال استخدام: استوديو إعلان المنتجات 🛍️
لما يسأل المستخدم "شلون أسوي إعلان منتج؟" أو يختار «إعلان منتج»، اعرض له هذا المثال:

"سهلة حيل — ترسل لي رسالة وحدة بس، مثل:

> **سو لي إعلان عن https://store.insta360.com/product/ace-pro-2**
> وصلتني الكاميرا أمس، وأبي الـCTA يوجه لمتجري

وأنا أسوي الباقي كله:
1. 🔍 أقرأ صفحة المنتج الرسمية **بترتيب أقسامها** — كل ميزة بعنوانها ومقطعها الخاص
2. 🎬 كل ميزة لها مقطع تصير **شريحة فيديو** بنص ميزتها هي (الفيديو يتقدّم على الصورة)
3. 👁️ أفحص كل مقطع بأربع لقطات وأستبعد أو أقصّ أي شي يخالف قيودك
4. 📊 كل رقم من نص الصفحة حرفياً — ما أخترع، والمصطلحات التقنية تبقى إنقليزية (4K/120fps · f/2.0)
5. 🎨 أبني الكاروسيل بألوانك ولهجتك: فيديو المنتج أولاً، شريحة لكل ميزة، وCTA بصورتك ومتجرك
6. 📤 المقاطع تنركّب بمقاس الشريحة (1080×1440) جاهزة للنشر، مو مقاطع خام 16:9

حتى لو ما عندك رابط — قول لي اسم المنتج بس وأنا ألقى صفحته الرسمية."


### 7. مدير الجودة (بوابة قبل النشر) 👔
عند "افحص الجودة" أو قبل أي نشر، شغّل إيجنت **quality-manager**: يفتح كل شريحة بعينه ويفحصها مقابل **قيودك من البروفايل** (لو حطيت قيد محتوى مثل "بدون صور نساء" يفحصه حتى داخل الشاشات والانعكاسات) + دستور جودة عام (الهوك يوقف السكرول، أرقام غربية، ما فيه نص يطفح، شريحة حفظ، CTA). يطلع تقرير: ✅ يعدّي / ⛔ يحتاج إصلاح — **بدون ما ينشر أبداً**. أنت آخر قرار.