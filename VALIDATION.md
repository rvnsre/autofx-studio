# Faktiki yoxlama nəticələri

Tarix: 10 noyabr 2026.

## Keçirilən yoxlamalar

- Python mənbələrinin compile yoxlaması: keçdi.
- CLI giriş nöqtəsi və `doctor`: keçdi.
- 26 unittest: keçdi; 0 xəta, 0 uğursuz test, 0 buraxılmış test.
- Sintetik video ilə real FFmpeg inteqrasiya testləri: keçdi.
- Audio və səssiz mənbələrin qarışdırılması: keçdi.
- 24, 25, 30, 50 və 60 FPS çıxışlar: keçdi.
- Audio sample sayı və master kadr sayı: yoxlandı.
- Musiqi analizi, musiqi qarışdırılması və `contain` rejimi: keçdi.
- Cache təkrar istifadəsi və qəsdən korlanmış klipin yenidən yaradılması: keçdi.
- Boşluq/Unicode olan media yolları: keçdi.
- Çıxışın təsadüfən əvəz edilməsinin qarşısının alınması: keçdi.
- LUT sırası, SFX müddəti və təkrarlana bilən nəticə: keçdi.
- JSON planlarının pozulması, NaN/Infinity və həddən böyük ədədlər: rədd edildi.
- FCP7 XML strukturu və AE skript escaping yoxlamaları: keçdi.
- Native adapter müqavilələri mock API ilə: keçdi.
- İstifadəçinin iki nümunə videosundan 4 saniyəlik, 360×640, 120 kadr və 6 kəsimli önbaxış yaradıldı; tam decode yoxlaması keçdi. Mənbə videolar dəyişdirilmədi.

Maşın tərəfindən oxunan nəticə: `validation.json`.

Önbaxış masteri layihə qovluğunun yanında `autofx-preview.mp4`, hesabatı isə `preview-report.json` kimi saxlanılıb. Mənbə ZIP-ə istifadəçi videoları və bu media daxil edilməyib.

## Lokal mühit

- Windows, build 26100.
- Python 3.11.9.
- OpenCV 5.0.0.
- NumPy 2.4.6.
- FFmpeg 7.1 essentials build.
- İnteqrasiya testlərinin ümumi müddəti təxminən 14.1 saniyə idi; bu, render sürəti üçün universal benchmark deyil.

## Bu sessiyada yoxlanılmayan hissələr

- Linux və macOS hostlarında faktiki icra. CI konfiqurasiyası hazırlanıb, uzaqda işə salınmayıb.
- Quraşdırılmış Resolve/Premiere/After Effects-də real import və native render. Native adapter testləri mock-lardır.
- NVENC/QSV/AMF/VideoToolbox avadanlıq sürətləndirilməsi.
- Bütün codec-lər, kamera formatları və professional rəng iş axınları.

Sıfır səhv və ya bütün yaradıcı nəticələrə zəmanət verilmir. Sübut edilən nəticələr yalnız yuxarıda göstərilən testləri əhatə edir.
