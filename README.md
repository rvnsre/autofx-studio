# AutoFX Studio 0.2

Terminaldan avtomatik qısa montaj, prosedural SFX, yaradıcı `.cube` LUT və video redaktorlarına ötürmə.

Bu layihə videoları lokal emal edir. Bulud hesabı, abunə, API açarı və ya media yükləməsi tələb etmir. İstifadəçinin nümunə videoları mənbə paketinə daxil edilməyib.

## Nələr edir?

- Səhnə histogramlarından kəsim namizədləri çıxarır; analiz maksimum 2400 kiçik kadrla məhdudlaşdırılır.
- Musiqi verilərsə enerji yüksəlişlərini tapır və kəsimləri yaxın namizədlərə uyğunlaşdırır.
- Planı tam kadr sərhədlərində qurur: 24, 25, 30, 50 və 60 FPS.
- Zoom/punch-in, qısa flash, sabit sürət dəyişməsi və rəng görünüşü tətbiq edir.
- Hər kəsim üçün whoosh və impact yaradır; səslər 48 kHz WAV olaraq saxlanılır.
- Videonu və PCM səsi ayrı render edir; AAC yalnız yekun masterdə kodlanır.
- Paralel klip renderi, SHA-256 ilə mənbə/cache yoxlaması, atomik master yazılması və proses ləğvi təmin edir.
- MP4 master, JSON plan/hesabat, `.cube`, WAV, FCP7 XML və AE JSX/manifest yaradır.
- Resolve-a ayrıca yeni layihə kimi import və seçilmiş yerli presetlə native render edə bilir.
- After Effects-də kompozisiya/AEP yaradan skript və ayrıca `aerender` əmri təqdim edir.

Bu, qaydalara əsaslanan montaj mühərrikidir. Mətn promptundan istənilən VFX səhnəsini generasiya edən model, nitqi anlayan redaktor, avtomatik rotoskopiya və ya nümunənin piksel səviyyəsində surəti deyil. Kəsimlər danışığı yarıda saxlaya bilər. Musiqi analizi musiqişünaslıq səviyyəsində beat/downbeat aşkarlanması deyil.

## Platformalar

| Hissə | Windows | Linux | macOS |
|---|---|---|---|
| CLI, FFmpeg render, LUT, SFX | Bəli | Bəli | Bəli |
| XML/JSX fayllarının yaradılması | Bəli | Bəli | Bəli |
| Native Resolve adapteri | Quraşdırılmış API/lisenziya tələb edir | Quraşdırılmış API/lisenziya tələb edir | Quraşdırılmış API/lisenziya tələb edir |
| Native Adobe adapterləri | AE quraşdırılması tələb edir | Adobe native versiyası yoxdur | AE quraşdırılması tələb edir |

Premiere üçün XML import yolu verilir; Premiere daxilində birbaşa headless idarəetmə iddia edilmir. Photoshop/Illustrator kimi video montajı ilə əlaqəsiz Adobe məhsulları bu layihənin əhatəsində deyil. Linux Resolve-da H.264 importu nəşr, versiya və codec dəstəyindən asılıdır; FFmpeg master yaradılması bundan asılı deyil.

## Quraşdırma

Python 3.10 və ya daha yenisini quraşdırın. Layihə qovluğunda:

```console
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe autofx.py doctor
```

Linux/macOS:

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python autofx.py doctor
```

Aktivləşdirilmiş virtual mühitdə aşağıdakı nümunələrdəki `python` və quraşdırılmış `autofx` əmri eyni funksiyanı yerinə yetirir. Python paketinin gətirdiyi FFmpeg istifadə edilə bilər; ayrıca ffprobe tələb edilmir. Alternativ olaraq FFmpeg-i sistem PATH-ına əlavə edin. Başqa binary seçmək üçün `AUTOFX_FFMPEG` dəyişənini həmin executable-ın tam yoluna təyin edin.

## Bir əmrlə render

```console
python autofx.py auto "video1.mp4" "video2.mp4" -o "renders/result.mp4" --preset hype --duration 15 --width 1080 --height 1920 --jobs 2
```

Musiqi və bütün təsviri kəsmədən yerləşdirmək:

```console
python autofx.py auto "video.mp4" -o "renders/music.mp4" --music "music.wav" --fit contain --preset cinematic
```

`cover` kadrı doldurmaq üçün kənarları kəsir. `contain` təsviri bütöv saxlayıb boş hissələri qara ilə doldurur. HDR/PQ/HLG mənbələr avtomatik SDR kimi rənglənmir: əvvəlcə ayrıca düzgün rəng idarəsi ilə SDR-ə çevirin. Yaradılan LUT Rec.709/display-referred yaradıcı görünüşdür; kamera LOG transformu deyil.

## Planı redaktə etmək və davam etmək

```console
python autofx.py plan "video.mp4" -o "edit.json" --duration 12 --no-analyze
python autofx.py render "edit.json" -o "renders/edit.mp4"
```

JSON daxilində `clips` siyahısındakı `in`, `speed`, `zoom`, `flash` dəyişilə bilər. `timeline_frame` və `frames` kəsimsiz, üst-üstə düşməyən timeline təşkil etməlidir. Köhnə 0.1 planları dəstəklənmir; schema 2 planını yenidən yaradın.

Eyni əmri təkrarlayanda tamamlanmış və hash-i uyğun kliplər yenidən istifadə olunur. Mövcud master üçün `--overwrite` lazımdır. Mənbə dəyişibsə planı yenidən yaradın. Elektrik kəsilməsindən qalan `.autofx.lock` faylını yalnız həmin çıxış üçün renderin işləmədiyini yoxladıqdan sonra əl ilə silin. Proqram başqa prosesin kilidini avtomatik silmir.

## Sürət və GPU

`--encoder cpu` standart, daha geniş uyğun variantdır. İstəyə görə `nvenc`, `qsv`, `amf`, `videotoolbox` seçilə bilər. `doctor` yalnız FFmpeg build-də encoderin olduğunu göstərir; GPU/driver işləkliyini sübut etmir. Uyğunsuz GPU xətası gizlədilmir və səssiz CPU keçidi edilmir.

Filtrlər, histogram analizi və zoom CPU-da işləyir. GPU seçimi video kodlayıcısını dəyişir. Sürət mənbə codec-i, disk, kadr ölçüsü və avadanlıqdan asılıdır; sabit real-time vədi verilmir. `--jobs` 1–8 arasında qəbul edilir; yüksək ölçüdə yaddaş üçün 1–2 seçin. `--skip-decode-check` əlavə tam decode yoxlamasını söndürür; kadr sayı, PCM uzunluğu və mənbə hash-ləri yenə yoxlanılır.

## Çıxışlar

Masterin yanında `result_assets/<hash>/` yaranır:

| Fayl | Məqsəd |
|---|---|
| `plan.json` | Dəqiq montaj planı və mənbə kimlikləri |
| `report.json` | Master hash-i, müddət, render vaxtı, çıxış yolları |
| `clip_*.mov` | Effektləri tətbiq edilmiş ayrıca video klipləri |
| `clip_*.wav` | Klipə uyğun, dəqiq nümunə saylı PCM səsi |
| `source_audio.wav` | Kəsimlər üzrə yığılmış ilkin səs |
| `sfx.wav` | Ayrı whoosh/impact stem-i |
| `look.cube` | Yaradıcı LUT |
| `timeline.xml` | Premiere/Resolve üçün kəsim timeline-ı |
| `after_effects.json` | AE import manifesti |
| `build_after_effects.jsx` | AE kompozisiya skripti |

XML/AE-də video klipləri ayrıdır, effektlər həmin kliplərə tətbiq olunub; native, parametrik VFX node-ları kimi ötürülmür. Timeline audio-su yekun masterdən götürülür. Bütün media qovluğunu masterlə birlikdə saxlayın; faylları köçürəndə redaktorda relink lazım ola bilər. Source hash-lər mütləq fayl yolları ilə saxlanılır; public repo-ya media/plan/hesabatları yoxlamadan əlavə etməyin.

## Resolve

Resolve-u başladın və quraşdırılmış nəşrin xarici scripting dəstəyini hazırlayın. Lazım gələrsə `RESOLVE_SCRIPT_API` və `RESOLVE_SCRIPT_LIB` dəyişənlərini vendor README-sinə uyğun qurun.

```console
python autofx.py resolve "renders/result_assets/HASH/timeline.xml"
python autofx.py resolve "renders/result_assets/HASH/timeline.xml" --render-dir "native-render" --render-preset "MyInstalledPreset"
```

Yeni unikal layihə yaradılır. Native rendering üçün mövcud render presetinin dəqiq adı lazımdır. Komanda lisenziya və tətbiqdə icazə parametrlərini dəyişmir.

## After Effects

AE-də boş layihə açın. Fayla yazmağa icazə verən scripting ayarları quraşdırılmış tətbiqdə hazır olmalıdır. Məsələn Windows-da öz versiyanızın executable yolunu göstərin:

```console
python autofx.py after-effects "renders/result_assets/HASH/after_effects.json" --exe "C:/Program Files/Adobe/Adobe After Effects 2025/Support Files/AfterFX.exe" --project "renders/native.aep"
```

macOS-da `--exe` tətbiqin `.app/Contents/MacOS/` daxilindəki uyğun executable yoludur. Mövcud media olan AE layihəsinə toxunmaqdan imtina edilir. Mövcud `.aep` əvəz edilmir. Launcher-in çıxmasını gözləmək əvəzinə skriptin nəticə bildirişi izlənir.

```console
python autofx.py aerender "renders/native.aep" --exe "/your/path/to/aerender" -o "renders/native.mov" --template "Your installed output module template"
```

Template adı AE quraşdırılmasına və dilinə uyğun olmalıdır. Çıxış formatı/uzantısı həmin template-lə uyğun seçilməlidir. Native tətbiqlər və adapterlər üçün ayrıca quraşdırılmış proqram/lisenziya tələb olunur.

## Yoxlamalar

Tam test dəstini bir əmrlə başladıb maşın tərəfindən oxunan hesabat saxlamaq:

```console
python tools/check.py --integration --report validation.json
```

Test temp qovluğunu ayrıca seçmək üçün `--temp-dir ./test-work` əlavə edin.

```console
python -m unittest discover -s tests -v
```

Sintetik video yaradan real render testləri üçün:

Windows PowerShell:

```powershell
$env:AUTOFX_INTEGRATION='1'
python -m unittest discover -s tests -v
```

Linux/macOS:

```sh
AUTOFX_INTEGRATION=1 python -m unittest discover -s tests -v
```

Unit testləri planların pozulması, NaN/Infinity, hash, kilid, proses vaxt limiti, audio tempo, LUT, SFX və XML-i yoxlayır. İnteqrasiya testləri qarışıq FPS, səssiz/səsli mənbə, Unicode/boşluqlu yol, musiqi, cache və korlanmış klipin bərpasını yoxlayır. CI üç OS üçün nəzərdə tutulub; CI faylının mövcudluğu həmin platformaların bu lokal sessiyada sınaqdan keçirildiyi demək deyil. Yerli faktiki nəticələr `VALIDATION.md` faylındadır.

## Məhdudiyyətlər

- Çıxış müddəti: 0.2–600 saniyə; 1–128 mənbə; maksimum 4096 klip.
- Sadə enerji analizi, qaydalara əsaslanan montaj və sabit sürət dəyişməsi var; generativ VFX, semantik kəsim və speed-ramp əyriləri yoxdur.
- HDR, kamera LOG, çoxkanallı professional audio və subframe timecode üçün ayrıca uyğun iş axını lazımdır.
- Native Resolve/Adobe davranışı quraşdırılmış tətbiq versiyası, edition, media codec-ləri və icazələrdən asılıdır.
- FFmpeg/numpy/OpenCV ayrıca layihələrdir; onların lisenziyaları özlərinə aiddir. Bu source paketə FFmpeg binary-si daxil edilmir.

## Rəsmi istinadlar

- [After Effects scripting](https://developer.adobe.com/after-effects/)
- [Adobe automated rendering](https://helpx.adobe.com/after-effects/desktop/render-and-export/automate-rendering/automated-rendering-network-rendering.html)
- [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html)
- Resolve scripting üçün quraşdırılmış məhsulun `Developer/Scripting/README.txt` sənədi əsasdır.
