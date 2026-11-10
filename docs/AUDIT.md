# AutoFX Studio 0.2.1 — kod auditi

Tarix: 10 noyabr 2026. Audit 0.2.0 mənbə kodunun faktiki icrası və xəta sərhədlərinin yoxlanmasına əsaslanır.

## Sübut

Əvvəlcə əvvəlki 28 testə 8 problemli ssenari əlavə edildi. Köhnə kodda bu yeni ssenarilər uğursuz oldu və ya idarə olunmayan xəta qaytardı: 36 testlik dəstdə 6 failure və 3 error vardı. Bir testin bir neçə subtesti olduğuna görə failure/error cəmi fərqli ssenari sayından çoxdur. [Əvvəlki nəticə](audit-before.json).

Düzəlişlərdən və əlavə müqavilə/inteqrasiya sınaqlarından sonra 43 test keçir: 0 failure, 0 error, 0 skip. Cari lokal nəticə layihə kökündəki `validation.json` faylıdır. Native tətbiq yoxlamaları mock müqavilələrdir; real Resolve/AE quraşdırılmasının sertifikasiyası deyil.

## Tapıntılar və düzəlişlər

| Problem | Əsas səbəb | Düzəliş və yoxlama |
|---|---|---|
| Anamorfik video dartılırdı | Scale ölçüləri piksel nisbətinə əsaslanır, sonra SAR=1 edilirdi | Ölçülər DAR əsasında seçilir. Real 2:1 SAR videoda letterbox və rəngli fiqurun nisbəti ölçülür. |
| Yarımçıq WAV qəbul edilirdi | Yalnız başlıqda yazılmış sample sayı yoxlanılırdı | PCM məlumatı hissələrlə tam oxunur; qısaldılmış fayl rədd edilir. |
| Nisbi FFmpeg yolu worker-də işləmirdi | Executable yoluna subprocess-in cache CWD-si təsir edirdi | Executable subprocess-dən əvvəl mütləq yola çevrilir. |
| Cover-art video seçilə bilərdi | İlk `Video:` sətri həmişə əsas video sayılırdı | Attached picture kənarlaşdırılır. Bir neçə əsas track-də səssiz seçim əvəzinə aydın xəta verilir. |
| Yanlış timeout tipi qəbul edilirdi | `bool` integer sayılır, çox böyük integer `isfinite`-də daşırdı | Tiplər dəqiq yoxlanılır və overflow idarə olunan xəta olur. |
| AE nisbi yolları yanlış qovluqda axtarırdı | Python və AE fərqli CWD ilə işləyirdi, hesablanan absolute yol payload-a yazılmırdı | Manifest yolları bir dəfə normallaşdırılır və JSX-ə absolute kimi verilir. |
| Native render uğursuzluğu yarımçıq fayl saxlayırdı | aerender birbaşa yekun təyinat yoluna yazırdı | Eyni filesystem-də staging və yalnız uğurdan sonra publication. |
| Handoff xətası əvvəlki masteri itirə bilərdi | Master ixrac metadata-sından əvvəl əvəz edilirdi | Handoff əvvəl hazırlanır; ixrac xətası zamanı əvvəlki master saxlanır. |

## Əlavə möhkəmləndirmə

- `exists()` və replacing rename arasındakı yarış əvəzinə atomik no-overwrite publication. Paralel yazıçının mövcud faylı qorunur.
- Renderdən sonra SHA-256 yenidən yoxlanılır. Mənbənin baytı dəyişdirilib əvvəlki timestamp qaytarıldıqda belə publication dayandırılır.
- Əvvəl `--skip-decode-check` ilə yaradılmış cache sonrakı verified renderdə decode edilir və yenidən encode edilmədən statusu yüksəldilir.
- Handoff-da `zip()` funksiyasının çatışmayan klipləri səssiz kəsməsinin qarşısı alınır.
- Renderer versiyası 0.2.1 oldu: köhnə, məsələn yanlış anamorfik nisbətli kliplər yeni cache kimi qəbul edilmir.
- Paket lisenziya metadatası SPDX formatına keçirildi; uyğun build backend minimumu göstərildi.

## İcranın sərhədləri

Lokal sübut Windows/Python 3.11/FFmpeg 7.1 üçündür. Linux/Windows/macOS üzrə GitHub Actions matrix-i ayrıca uzaq nəticədir. GPU encoderləri və real Adobe/Resolve sessiyaları bu lokal auditdə işə salınmayıb. Sadə səhnə və musiqi analizi semantik AI redaktəsi kimi təqdim edilmir. Bütün mümkün media formatlarının xətasız işləməsinə zəmanət verilmir.
