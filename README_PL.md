# Krea 2 Turbo — Prompt Builder v0.1.2 (ComfyUI)

**Wersja alfa do prób.** Wygenerowany obraz → analiza sceny → lista co zostawić i co poprawić → ulepszony prompt en-US. Jeden obraz, nie ranking dwóch obrazów.

## Założenia

- Ollama: **nie**. Zewnętrzne API / chmura do analizy: **nie**.
- Modele i `llama.cpp` wolno pobierać / aktualizować przez internet **przed uruchomieniem analizy**; sam Prompt Builder nie pobiera niczego.
- Przy każdym wykonaniu startuje **osobny, krótko żyjący proces `llama-cli`**, po zakończeniu znika. Przy timeout zabijamy całe drzewo procesu. ComfyUI nie musi trzymać VLM-a w swojej pamięci Pythona.
- Model musi być **multimodalny**, a nie tylko modelem tekstowym/enkoderem CLIP. Samo `*.gguf` bez odpowiedniego projektora wizji nie wystarczy.
- Można użyć np. zgodnej wersji Gemma 4 / Qwen3.5 po abliteration. **Nie wszystkie repozytoria „abliterated” zawierają działający tor obrazu.** Sprawdź wydanie i zgodność z `llama.cpp`.
- Domyślny limit to **24 warstwy na GPU**, 4096 kontekstu i 1280 px maksymalnego boku obrazu; to punkty startowe, nie gwarancja zajętości 12 GB VRAM.

## Instalacja

1. Wypakuj projekt do `ComfyUI/custom_nodes/ComfyUI-Krea2Turbo-PromptBuilder/`.
2. Pobierz lokalną binarkę najnowszego kompatybilnego `llama.cpp` z `llama-cli` (Windows: `llama-cli.exe`). Trzymaj ją poza folderem projektu albo dodaj do PATH.
3. Umieść **model GGUF i zgodny mmproj** w dowolnym z już używanych katalogów: `ComfyUI/models/llama_cpp/`, `ComfyUI/models/LLM/`, `ComfyUI/models/text_encoders/` lub dawnym `ComfyUI/models/krea_prompt_builder/`. **Nie kopiuj modelu drugi raz.** Obsługiwane są też dodatkowe ścieżki z `folder_paths` (np. `extra_model_paths.yaml`).
4. Zrestartuj ComfyUI, dodaj **Krea 2 Turbo | Prompt Builder v0.1.2** i wybierz model z listy. `mmproj_gguf` może pozostać na `[AUTO: projector next to model]`. Jeśli widzisz stary node, odśwież przeglądarkę lub dodaj node ponownie.
5. Wpisz ścieżkę `llama_cli_path` do pliku wykonywalnego (np. `D:\\AI\\llama.cpp\\build\\bin\\Release\\llama-cli.exe`) albo `llama-cli`, jeśli jest w PATH.

## Podłączenie obrazu

W nowszych ComfyUI `Save Image` ma wyjście `images` typu `IMAGE`. Podłącz je do `image` w Prompt Builderze. Jeśli Twoje `Save Image` nie ma wyjścia, rozgałęź `IMAGE` jeszcze przed `Save Image` i skieruj drugi przewód do Prompt Buildera.

Jeżeli **RAM/VRAM Purge** ma wyjście, dołącz je do opcjonalnego wejścia `after_purge`, co wymusi wykonanie oczekujących węzłów wejściowych przed analizą. Jeśli Twój Purge **nie** wystawia wyjścia, dodaj między nim a Prompt Builderem własny element porządkujący wykonanie — samo ułożenie węzłów na canvasie nie ustala kolejności.

**Uwaga:** połączenie `after_purge` nie uruchamia Purge ani nie gwarantuje pełnego zwolnienia RAM/VRAM; odpowiada za zależność w grafie. Obraz podłączony jako wejście nadal może zajmować pamięć.

## Pola wejściowe

| Pole | Znaczenie |
|---|---|
| `image` | Jeden tensor obrazu/batch `IMAGE`; `image_index` wybiera pojedynczą klatkę |
| `model_gguf`, `mmproj_gguf` | Wagi VLM z `llama_cpp` / `LLM` / `text_encoders` / innych zarejestrowanych katalogów. Projektor może być znaleziony automatycznie, jeśli jest jednoznaczny |
| `model_path_override`, `mmproj_path_override` | Opcjonalne **bezwzględne** ścieżki do dowolnych lokalnych plików GGUF poza ComfyUI; pola zastępują wybór z listy. Żadnego kopiowania. |
| `llama_cli_path` | Pełna ścieżka do binarki `llama-cli` |
| `mode` | `faithful`, `improve` (domyślnie), `creative` |
| `user_goal` | Własna instrukcja (PL lub EN) |
| `source_prompt` | Opcjonalny oryginalny prompt; pomaga zachować zamiar autora |
| `gpu_layers` | Liczba warstw przeniesionych do VRAM; 0 = CPU |
| `vision_gpu` | Czy projektor wizualny ma działać na GPU |
| `commit_headroom_gib` | Minimalny zapas pamięci zatwierdzonej systemu, domyślnie 6 GiB |
| `timeout_seconds` | Po przekroczeniu limitu proces VLM jest kończony |
| `after_purge` | Opcjonalne wejście synchronizacyjne przyjmujące dowolny typ |

## Wyjścia

- `prompt_en_us` (`STRING`): gotowy prompt po angielsku dla modelu Krea 2 Turbo.
- `scene_analysis_en` (`STRING`): analiza tego, co rzeczywiście widać w obrazie.
- `edit_plan_en` (`STRING`): sekcje `KEEP` i `IMPROVE`.
- `image` (`IMAGE`): niezmieniony tensor wejściowy, do dalszego połączenia.

Wersja 0.1 generuje JSON w **jednym wywołaniu VLM**. Node rozdziela pola i nie próbuje „poprawiać” rezultatu innym modelem. Przy niepoprawnym JSON zwraca błąd zamiast wprowadzać śmieci do promptu.

## RAM/VRAM

Masz 64 GB RAM, ale niewielki zapas po stronie **Committed** może uniemożliwić nową alokację pomimo pozornie wolnych GB RAM-u. Wersja 0.1 sprawdza przybliżony zapas pamięci zatwierdzonej systemu (Windows: `GetPerformanceInfo`; Linux: `/proc/meminfo`) i może przerwać ładowanie przed awarią. Nie sprawdza jeszcze rzeczywistego zużycia VRAM przez inne procesy. Dodatkowo kontrolujemy `gpu_layers`, `context_size`, `batch_size` oraz maksymalny rozmiar obrazu.

Jeżeli nie da się odczytać zapasu commit, diagnostyka trafia do logu, a uruchomienie nie jest blokowane.

## Prywatność

Program nie implementuje wysyłania promptów ani obrazów na internetowe API. Wewnętrzny `llama-cli` dostaje `--offline`, a pliki `.png` są tworzone w lokalnym katalogu tymczasowym i usuwane po wykonaniu. **Nie jest to pełna izolacja sieciowa** obcej binarki; dla twardej gwarancji prywatności zablokuj jej wyjście do internetu w zaporze systemu.

## Aktualny status

Testy jednostkowe oraz test symulujący `llama-cli` są przewidziane w `tests/`. **Brak jeszcze realnego testu na GPU 12 GB z konkretnymi wagami Gemma 4/Qwen3.5.** To alfa V0.1, a nie deklaracja pełnej zgodności sprzętowej.

## Publikacja na GitHub

Jeśli repozytorium nie istnieje, utwórz **puste** `piksel-90/ComfyUI-Krea2Turbo-PromptBuilder` na GitHubie. Projekt ma już przygotowany lokalny commit i tag `v0.1.0`.

W katalogu repozytorium wykonaj `scripts/publish-after-repo-created.ps1` (PowerShell) lub `scripts/publish-after-repo-created.sh` (Bash), przy działającym uwierzytelnieniu Git. Alternatywnie zaimportuj załączony plik `.bundle` jako lokalne repo i wypchnij `main` i `v0.1.0`.


## Diagnostyka V0.1.1 — pusta lista modeli / llama-cli

W wersji **0.1** model był błędnie wyszukiwany **wyłącznie** w `models/krea_prompt_builder`. Wersja **0.1.1** naprawia ten problem. Dla Windows Portable typowa ścieżka modelu to np.:

```text
D:\ComfyUI_windows_portable_2\ComfyUI\models\llama_cpp\gemma-4-12B-it-abliterated-uncensored.Q5_K_M.gguf
D:\ComfyUI_windows_portable_2\ComfyUI\models\llama_cpp\gemma-4-12B-it-abliterated-uncensored.mmproj-f16.gguf
```

Po instalacji nowej wersji **zrestartuj ComfyUI** i sprawdź dropdown `model_gguf`. Nie wystarczy samo przeładowanie workflow, bo ComfyUI cache'uje definicje nodów. Listy są oznaczone prefiksem katalogu, np. `llama_cpp :: gemma...gguf`. Alternatywnie wklej pełną ścieżkę do `model_path_override` i opcjonalnie do `mmproj_path_override`. Foldery spoza standardowych katalogów można dodać przez zmienną środowiskową `KREA_PROMPT_BUILDER_MODEL_DIRS` (w Windows rozdzielaj katalogi średnikiem) ustawioną **przed** uruchomieniem ComfyUI.

`llama-cli.exe` jest **osobnym programem**; posiadanie GGUF i `mmproj` **nie instaluje** go. Pobierz kompatybilną z GPU paczkę Windows z [oficjalnych wydań llama.cpp](https://github.com/ggml-org/llama.cpp/releases), wypakuj i ustaw `llama_cli_path` na pełną ścieżkę do `llama-cli.exe`. Nie wpisuj tutaj ścieżki GGUF. V0.1.1 nie pobiera żadnego programu ani pliku samodzielnie. `llama.cpp` musi wspierać architekturę wybranego VLM i projektora — tego jeszcze nie potwierdziliśmy na rzeczywistej Gemmie 4.

**Prywatność:** uruchamianie binarki lokalnie nie stanowi samo w sobie gwarancji izolacji sieciowej. Należy używać zaufanej binarki i dla pełnej pewności zablokować jej dostęp do sieci w zaporze. Node przekazuje `--offline` i nie używa zewnętrznych endpointów.


## V0.1.2: poprawka dla Gemmy 4 — brak wynikowego JSON

W V0.1.1 zawsze podawaliśmy `-jf schema.json`, a parser wymagał pełnego JSON-u. W niektórych konfiguracjach Gemma 4/llama.cpp generuje zamiast niego dodatkowe rozumowanie albo inny format i node zgłasza ten sam błąd nawet po zmniejszeniu rozmiaru obrazu. **V0.1.2 nie wymusza JSON-u domyślnie.** Prosi o 4 sekcje `[ANALYSIS]`, `[KEEP]`, `[IMPROVE]`, `[PROMPT]`, przy czym parser nadal obsługuje JSON. Nie oznacza to jeszcze potwierdzenia kompatybilności Twojego GGUF/MMProj z binarką.

### Nowe pola (na samym końcu ustawień)

| Pole | Zalecenie dla RTX 4070 12 GB / Gemma 4 |
|---|---|
| `execution_device` | `cpu` do testu bez GPU, potem `hybrid` |
| `gpu_layers` | Używane w `hybrid` (np. 12–16). Ignorowane w `cpu` oraz `gpu` |
| `vision_gpu` | `false` na początek. W `cpu` zawsze wyłączone |
| `output_mode` | **`plain_sections`**. `json_schema` tylko na świadomy test |
| `reasoning` | **`off`** (wyłącza myślenie i ustawia budżet na 0) |
| `save_diagnostics` | `false` na stałe, `true` gdy potrzebne surowe logi |

**Test CPU**: `execution_device=cpu`, `vision_gpu=false`, `output_mode=plain_sections`, `reasoning=off`, `max_image_side=768`, `context_size=4096`, `max_tokens=900`, `timeout_seconds=600`. Powinien wymagać RAM i być wolniejszy, ale testuje czy powstaje poprawny prompt bez CUDA. Tryb `gpu` oznacza próbę przeniesienia wszystkich warstw do VRAM i może wywołać OOM przy zajętości VRAM po Krea. `hybrid` służy do sterowania ilością offloadu przez `gpu_layers`.

### Lokalna diagnostyka, gdy odpowiedź dalej jest nieczytelna

Włącz `save_diagnostics=true` na **jedno wykonanie**. Pliki znajdziesz w:

```text
D:\ComfyUI_windows_portable_2\ComfyUI\output\krea_prompt_builder_diagnostics\vlm_...\
  result.txt
  stdout.txt
  stderr.txt
  meta.json
```

Przy błędzie node wyświetli lokalną ścieżkę do zapisanych plików. Pliki **mogą zawierać prywatny prompt i opis obrazu**. Nie publikuj ich na GitHubie, nie wysyłaj całego logu, jeśli są tam dane prywatne; wystarczy przekazać krótki opis lub zanonimizowany fragment. Po zdiagnozowaniu wyłącz diagnostykę i usuń foldery testowe. Bez włączenia tej opcji nie zapisujemy wyników do trwałych plików.

**Instalacja:** podmień cały katalog dodatku plikami V0.1.2, nie kopiuj GGUF ani `mmproj` ponownie. Zrestartuj ComfyUI i odśwież przeglądarkę; jeśli stare widgety zostaną w istniejącym nodzie, usuń tylko stary Prompt Builder i dodaj go ponownie, podpinając dotychczasowe przewody. `llama-cli.exe` zostaje tam, gdzie go zainstalowałeś.

**Uwaga:** projekt nadal wymaga realnego testu z Twoim `llama.cpp` b11719 / Gemma 4 / RTX 4070. Testy jednostkowe nie dowodzą, że model widzi obraz w tej konfiguracji.
