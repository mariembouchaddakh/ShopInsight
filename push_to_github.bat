@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Envoi de ShopInsight sur GitHub ===
where git >nul 2>&1
if errorlevel 1 (
  echo Git n'est pas installe. Installez-le depuis https://git-scm.com/download/win puis relancez ce fichier.
  pause
  exit /b 1
)
echo.
echo Collez l'adresse de votre depot vide, par exemple :
echo   https://github.com/VOTRE_NOM/ShopInsight.git
set /p URL=Adresse du depot : 
if "%URL%"=="" (
  echo Aucune adresse saisie.
  pause
  exit /b 1
)
git remote remove origin >nul 2>&1
git remote add origin %URL%
git branch -M main
git push -u origin main
if errorlevel 1 (
  echo.
  echo L'envoi a echoue. Verifiez l'adresse et que le depot GitHub est bien vide.
  pause
  exit /b 1
)
echo.
echo Termine : le projet est sur GitHub.
pause
