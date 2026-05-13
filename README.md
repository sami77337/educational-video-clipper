# Educational Video Clipper

A Windows desktop app for turning educational videos into sorted short clips. The app supports YouTube URLs, local video files, pasted Arabic clip lists, Excel/CSV imports, automatic clip cutting with ffmpeg, ZIP export, and a final processing report.

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
- Avoid very old ZIP tools that do not support Unicode filenames
- Use Windows Explorer or modern ZIP tools to view results

### Windows Permissions

If the app cannot create folders or write files:

- Move the project to a writable folder such as Documents
- Avoid protected folders such as `C:\Program Files`
- Check antivirus or controlled folder access settings
- Run Command Prompt normally first; use administrator mode only if you understand why it is needed

## Packaging

This project is not packaged as an EXE yet.
