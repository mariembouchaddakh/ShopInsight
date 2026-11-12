@echo off
REM REHEARSE - traduction locale des avis Olist (portugais -> francais)
REM Double-cliquer sur ce fichier. Aucun avis n'est envoye en ligne ;
REM seuls les modeles (~600 Mo) sont telecharges une fois depuis Hugging Face.
REM Si la fenetre est fermee, relancer : le travail deja fait est conserve (cache).

cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

set PY=python
where python >nul 2>nul || set PY="%USERPROFILE%\anaconda3\python.exe"

echo === 1/3 Verification des dependances ===
%PY% -c "import torch" 2>nul || %PY% -m pip install torch --index-url https://download.pytorch.org/whl/cpu
%PY% -m pip install "transformers>=4.40" sentencepiece sacremoses
if errorlevel 1 goto erreur

echo.
echo === 2/3 Test rapide sur 200 avis ===
%PY% src\translate_reviews.py --project-dir . --limit 200
if errorlevel 1 goto erreur

echo.
echo === 3/3 Traduction complete (environ 1 h, le temps restant s'affiche) ===
%PY% src\translate_reviews.py --project-dir .
if errorlevel 1 goto erreur

echo.
echo Termine. Resultat : data\silver\reviews_text_fr.jsonl.gz
echo Echantillon a relire : quality\translation_sample_for_review.csv
pause
exit /b 0

:erreur
echo.
echo Une erreur s'est produite. Le detail est affiche ci-dessus.
pause
exit /b 1
