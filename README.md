# المقص البسيط

**المقص البسيط** تطبيق Windows بواجهة عربية لقص المقاطع التعليمية من فيديو محلي أو من رابط YouTube، مع دعم الاستيراد الذكي من الرسائل، واستيراد Excel/CSV، والتصنيف حسب المدة، والاستثناءات من وسط المقطع، وحفظ النتائج في مجلدات واضحة مع تقرير نهائي.

## الميزات الأساسية

- اختيار فيديو من الجهاز أو تنزيل فيديو من رابط YouTube.
- جدول مقاطع يدعم العناوين العربية.
- استيراد ذكي لرسائل واتساب/تلغرام وتحويلها إلى مقاطع قابلة للمراجعة.
- استيراد المقاطع من Excel أو CSV.
- دعم أوقات مرنة مثل `4:15` و `00:04:15` و `٤:١٥`.
- دعم الاستثناءات داخل المقطع، مثل حذف جزء من الوسط.
- قواعد تصنيف قابلة للتخصيص لإنشاء عدة مجلدات حسب مدة المقطع.
- حفظ النتائج داخل مجلد النتائج مباشرة بدون إنشاء ملف ZIP افتراضيًا.
- إنشاء تقرير قص نهائي.

## Windows Setup

### 1. Install Python

Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/windows/).

During installation, enable:

- Add python.exe to PATH
- pip

After installation, open Command Prompt or PowerShell and check:

```powershell
python --version
```

### 2. Create a Virtual Environment

From the project folder:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

### 3. Install Requirements

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Run the App

```powershell
python app.py
```

Or double-click:

```bat
run_app.bat
```

### 5. Run Tests

```powershell
python -m pytest
```

Or double-click:

```bat
run_tests.bat
```

## Using the Batch Files

`run_app.bat` will:

- Create `.venv` if it does not exist
- Activate `.venv`
- Install `requirements.txt`
- Run `python app.py`

`run_tests.bat` will:

- Create `.venv` if it does not exist
- Activate `.venv`
- Install `requirements.txt`
- Run `python -m pytest`

## ffmpeg Requirement

Video cutting requires `ffmpeg`.

Install ffmpeg for Windows, then make sure `ffmpeg.exe` is available in PATH. Test it with:

```powershell
ffmpeg -version
```

## Troubleshooting

### ffmpeg Not Found

If the app shows `لم يتم العثور على ffmpeg`, install ffmpeg and add its `bin` folder to Windows PATH. Restart Command Prompt, PowerShell, or the app after updating PATH.

### yt-dlp Errors

YouTube downloads depend on `yt-dlp` and the availability of the video. If downloading fails:

- Check that the URL is correct
- Try updating dependencies with `python -m pip install --upgrade yt-dlp`
- Make sure the video is public or accessible
- Try again later if YouTube is temporarily blocking the request

### Python Not Found

If Windows says `python` is not recognized:

- Reinstall Python and enable `Add python.exe to PATH`
- Try `py --version`
- Replace `python` with `py` in commands if needed

### Arabic Filenames

The app supports Arabic project names and clip titles. If Arabic filenames look incorrect:

- Keep the project inside a normal Windows user folder such as Documents
- افتح مجلد النتائج من داخل التطبيق أو من Windows Explorer

### Windows Permissions

If the app cannot create folders or write files:

- Move the project to a writable folder such as Documents
- Avoid protected folders such as `C:\Program Files`
- Check antivirus or controlled folder access settings
- Run Command Prompt normally first; use administrator mode only if you understand why it is needed

## Branding Assets

The application icon and logo assets live in:

```text
assets/icon.svg
assets/icon.png
assets/icon.ico
```

They show a scissors-and-video-strip concept for **المقص البسيط**.

## Packaging

يمكن بناء نسخة Windows محمولة باستخدام ملفات البناء الموجودة في هذا المستودع.


## ملاحظة مهمة حول خطأ Windows Long Path

إذا ظهر خطأ أثناء تثبيت `PySide6` متعلقًا بطول المسار، فهذه النسخة تستخدم بيئة افتراضية قصيرة خارج مجلد المشروع:

```text
%USERPROFILE%\almiqs-albaseet-venv
```

لذلك شغّل التطبيق دائمًا عبر:

```text
run_app.bat
```

ولا تنشئ بيئة `.venv` داخل مجلد المشروع يدويًا.

## إصدار التطبيق كبرنامج Windows

لإنشاء نسخة تطبيق عادية تعمل من ملف `.exe`:

1. افتح مجلد المشروع.
2. شغّل الملف:

```bat
build_app.bat
```

3. بعد انتهاء البناء ستجد التطبيق هنا:

```text
dist\AlmiqsAlBaseet\AlmiqsAlBaseet.exe
```

هذه نسخة محمولة Portable. يمكن نسخ مجلد `dist\AlmiqsAlBaseet` كاملًا إلى أي جهاز Windows. يظهر الاختصار على سطح المكتب باسم **المقص البسيط**، بينما تبقى أسماء الملفات الداخلية إنجليزية لتجنب مشاكل ترميز Windows.

> ملاحظة مهمة: يعتمد التطبيق عند القص على وجود `ffmpeg` في الجهاز أو ضمن PATH. إذا ظهر خطأ ffmpeg، ثبّت FFmpeg أو أضفه إلى PATH قبل استخدام القص.



## تشغيل البرنامج من سطح المكتب

إذا أردت أن يظهر البرنامج على سطح المكتب باسم **المقص البسيط**:

1. فك الضغط عن المجلد في مكان ثابت، مثل `C:\app` أو على سطح المكتب.
2. شغّل الملف:

```bat
install_desktop.bat
```

سيتم إنشاء اختصار على سطح المكتب باسم **المقص البسيط** مع الأيقونة.

> لا تنقل ملف `.exe` وحده إلى سطح المكتب إذا بنيت نسخة `dist`؛ يجب إبقاء مجلد التطبيق كاملًا مع ملفاته، أو استخدم الاختصار الذي ينشئه البرنامج.

## بناء نسخة تطبيق Windows

لإنشاء نسخة تطبيق قابلة للتشغيل مثل البرامج العادية، شغّل:

```bat
build_app.bat
```

للبناء الآلي أو التحقق غير التفاعلي بدون فتح Explorer وبدون انتظار ضغط زر، شغّل:

```bat
build_app_ci.bat
```

بعد البناء، يمكن فحص حزمة الإصدار قبل إرسالها للفريق:

```powershell
python scripts\check_release_package.py
```

ولتشغيل الاختبارات وفحص تشغيل التطبيق والبناء وفحص الحزمة دفعة واحدة:

```bat
verify_release.bat
```

سينتج مجلد:

```text
dist\AlmiqsAlBaseet
```

وسيتم إنشاء اختصار على سطح المكتب باسم **المقص البسيط** يشغّل التطبيق من هذا المجلد.


## حل مشكلة يوتيوب: Sign in to confirm you're not a bot

أضيف خيار داخل واجهة البرنامج باسم **استخدام تسجيل الدخول من المتصفح**.
عند ظهور خطأ يوتيوب الذي يطلب تسجيل الدخول أو التأكد أنك لست روبوتًا:

1. سجّل دخولك إلى يوتيوب من المتصفح.
2. يفضّل إغلاق المتصفح قبل بدء التنزيل.
3. فعّل خيار **استخدام تسجيل الدخول من المتصفح** داخل البرنامج.
4. اختر المتصفح المناسب: Chrome أو Edge أو Brave أو Firefox.
5. ابدأ القص من رابط يوتيوب.

البرنامج لا يحفظ Cookies ولا يطبعها في السجل؛ يستخدمها محليًا أثناء التنزيل فقط.
الجودة تبقى أفضل جودة فيديو وأفضل جودة صوت.

## تشغيل نسخة المصدر بدون نافذة CMD

إذا كنت تختبر نسخة المصدر ولا تريد ظهور نافذة CMD السوداء، شغّل:

```text
START_APP_NO_CONSOLE.vbs
```

أما `run_app.bat` فهو للتشخيص فقط، وسيُظهر نافذة CMD طبيعيًا.
