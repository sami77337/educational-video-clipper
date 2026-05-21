# دليل تجهيز حزمة الإصدار

هذا الدليل مخصص لمن يجهز نسخة Windows لإرسالها للفريق. الهدف أن تصل للفريق نسخة جاهزة للتشغيل، وليست ملفات المصدر.

## أين توجد النسخة المبنية

بعد تشغيل:

```bat
verify_release.bat
```

أو:

```bat
build_app_ci.bat
```

تكون النسخة المحمولة هنا:

```text
dist/AlmiqsAlBaseet
```

هذا المجلد هو حزمة التطبيق المحمولة التي يمكن اختبارها قبل الإرسال.

## ماذا نرسل للفريق

أرسل للفريق أحد الخيارين:

- مجلد `dist/AlmiqsAlBaseet` كاملًا بعد نجاح الفحص.
- ملف المثبت الناتج داخل `release/installer` إذا تم بناء المثبت باستخدام Inno Setup.

يجب أن تحتوي الحزمة على:

- `AlmiqsAlBaseet.exe`
- مجلد `_internal`
- `ffmpeg.exe`
- `README_AR.txt`
- ملفات التشغيل والموارد التي يضعها PyInstaller داخل الحزمة

## ماذا لا نرسل للفريق

لا ترسل ملفات أو مجلدات التطوير، مثل:

- `app.py`
- `src`
- `tests`
- `requirements.txt`
- `requirements-build.txt`
- `run_app.bat`
- `build_app.bat`
- `build_app_ci.bat`
- `verify_release.bat`
- `build_installer.bat`
- `scripts`
- `docs`
- `installer`
- `.git`
- `.pytest_cache`
- `__pycache__`
- `build`

ملفات المصدر لا تُرسل للفريق. الفريق يحتاج النسخة المبنية فقط.

## كيف نشغل البرنامج

من داخل مجلد الحزمة:

```text
dist/AlmiqsAlBaseet
```

شغّل:

```text
AlmiqsAlBaseet.exe
```

لا تنقل ملف exe وحده خارج المجلد؛ يجب إبقاء المجلد كاملًا لأن التطبيق يحتاج ملفات التشغيل الموجودة معه.

## كيف نتحقق أن الحزمة سليمة

شغّل:

```bat
verify_release.bat
```

أو بعد البناء فقط:

```powershell
python scripts\check_release_package.py
```

يجب أن يظهر أن الحزمة جاهزة مبدئيًا، وأن ملفات المصدر والاختبارات غير موجودة داخل الحزمة.

## تجهيز المثبت

تم تجهيز سكربت Inno Setup هنا:

```text
installer/AlmiqsAlBaseet.iss
```

لبناء المثبت شغّل:

```bat
build_installer.bat
```

إذا لم يكن Inno Setup مثبتًا، سيظهر تنبيه عربي واضح، وسيبقى سكربت المثبت جاهزًا لمن يملك أداة البناء.

إذا تم بناء المثبت بنجاح، سيكون الناتج في:

```text
release/installer
```

## ملاحظة عن ZIP

التطبيق لا ينشئ ملف ZIP لنتائج الفيديو افتراضيًا. النتائج تحفظ مباشرة داخل مجلد النتائج مع التقرير النهائي.
