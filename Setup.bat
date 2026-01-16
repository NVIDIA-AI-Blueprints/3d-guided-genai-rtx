@echo off
:: Check for Administrator privileges
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo This script requires administrative privileges.
    echo Attempting to elevate...
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\elevate.vbs"
    echo UAC.ShellExecute "cmd.exe", "/c ""%~f0""", "", "runas", 1 >> "%temp%\elevate.vbs"
    cscript //nologo "%temp%\elevate.vbs"
    del "%temp%\elevate.vbs"
    exit /b
)

:check_hf_token
setlocal EnableDelayedExpansion
echo.
set "HF_TOKEN_CHECK=%HF_TOKEN%"
if "%HF_TOKEN%"=="" (
    :enter_token_loop
    echo A Huggingface token is not set. A Huggingface token is required for this blueprint,
    echo provide your Huggingface token to continue the installation.
    echo.
    set /p "hf_token_input=Enter your Huggingface token (starts with 'hf_') or type 'n' to skip: "
    set "hf_token_input_lower=!hf_token_input!"
    for %%i in (A B C D E F G H I J K L M N O P Q R S T U V W X Y Z) do set "hf_token_input_lower=!hf_token_input_lower:%%i=%%i!"
    if /i "!hf_token_input_lower!"=="n" (
        echo Skipping Huggingface token entry.
        echo Huggingface token required for blueprint setup.
        goto :user_terminated
    ) else if "!hf_token_input:~0,3!"=="hf_" (
        echo Setting HF_TOKEN...
        setx HF_TOKEN "!hf_token_input!"
        echo HF_TOKEN set.
        goto :prompt_continue
    ) else (
        echo Invalid token format. Token must start with "hf_" or you must type 'n' to skip.
        goto :enter_token_loop
    )
) else (
    goto :prompt_continue
)

:user_terminated
echo Installation terminated...
goto :END

:prompt_continue
echo.
echo This blueprint will install the following third party software:
echo     *  Blender 4.2 LTS - license - https://www.blender.org/about/license/
echo     *  MICROSOFT VISUAL C++ 2015 - 2022 RUNTIME - license - https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/
echo     *  MICROSOFT VISUAL STUDIO 2022 - BUILD TOOLS - license - https://visualstudio.microsoft.com/license-terms/vs2022-ga-diagnosticbuildtools/
echo By installing this blueprint you accept the license agreements for the third party software shown above.
:prompt_loop
set "choice="
set /p "choice=Do you want to continue (y/n)? "
:: Remove leading/trailing spaces
for /f "tokens=*" %%i in ("!choice!") do set "choice=%%i"
:: Convert to lowercase
set "choice_lower=!choice!"
:: Explicitly map uppercase to lowercase for each letter
set "choice_lower=!choice_lower:A=a!"
set "choice_lower=!choice_lower:B=b!"
set "choice_lower=!choice_lower:C=c!"
set "choice_lower=!choice_lower:D=d!"
set "choice_lower=!choice_lower:E=e!"
set "choice_lower=!choice_lower:F=f!"
set "choice_lower=!choice_lower:G=g!"
set "choice_lower=!choice_lower:H=h!"
set "choice_lower=!choice_lower:I=i!"
set "choice_lower=!choice_lower:J=j!"
set "choice_lower=!choice_lower:K=k!"
set "choice_lower=!choice_lower:L=l!"
set "choice_lower=!choice_lower:M=m!"
set "choice_lower=!choice_lower:N=n!"
set "choice_lower=!choice_lower:O=o!"
set "choice_lower=!choice_lower:P=p!"
set "choice_lower=!choice_lower:Q=q!"
set "choice_lower=!choice_lower:R=r!"
set "choice_lower=!choice_lower:S=s!"
set "choice_lower=!choice_lower:T=t!"
set "choice_lower=!choice_lower:U=u!"
set "choice_lower=!choice_lower:V=v!"
set "choice_lower=!choice_lower:W=w!"
set "choice_lower=!choice_lower:X=x!"
set "choice_lower=!choice_lower:Y=y!"
set "choice_lower=!choice_lower:Z=z!"
:: Debug output to diagnose input
:: echo DEBUG: Raw input='%choice%', Lowercase input='%choice_lower%'
:: Validate input
if "!choice_lower!"=="y" (
    echo Continuing...
    goto :start_install
) else if "!choice_lower!"=="n" (
    echo Exiting...
    goto :END
) else (
    echo Invalid input. Please enter 'y' or 'n'.
    goto :prompt_loop
)

:start_install
pushd "%~dp0"
echo Running with administrator privileges.

set "distro_name=NVIDIA-Workbench"
echo Checking for WSL distribution "%distro_name%"...
wsl -d %distro_name% echo OK >nul 2>&1
set "distro_exists=!errorlevel!"
if !distro_exists! equ 0 (
    echo "%distro_name%" found.
    echo Checking if Podman is installed in "%distro_name%"...
    wsl -d %distro_name% podman --version >nul 2>&1
    set "podman_installed=!errorlevel!"
    if !podman_installed! equ 0 (
        echo Podman is installed in "%distro_name%"
        goto :WSL_Ready
    ) else (
        echo Podman is NOT installed in "%distro_name%"
        echo AI Workbench is installed, but not fully configured for this blueprint.
        echo Please open NVIDIA AI Workbench and configure Podman before re-running the blueprint installer.
        goto :WSL_Not_Ready
    )
) else (
    echo "%distro_name%" was not found...
    echo Please download and complete the NIMSetup installation, a restart will be required,
    echo then re-run the blueprint installer.
    echo Download link: https://assets.ngc.nvidia.com/products/api-catalog/rtx/NIM_Prerequisites_Installer_03052025.zip
    goto :WSL_Not_Ready
)

:WSL_Not_Ready
echo.
echo Script completed with prerequisites not fully met.
pause
exit /b 1

:WSL_Ready
echo NVIDIA-Workbench is properly configured for this blueprint
set "base_dir=%cd%"
set "comfyui_install_dir=.\ComfyUI_windows_portable\"

IF "%~1"=="" (
    GOTO :CheckExistingComfyInstall
)

:ProcessArg
if "%~1"=="" goto :CheckExistingComfyInstall
IF /I "%1"=="-i" (
    ECHO Custom ComfyUI Path provided:
    IF EXIST "%2" (
        IF "%2:~-1%" NEQ "\" (
            set "comfyui_install_dir=%2\"
        ) ELSE (
            set "comfyui_install_dir=%2"
        )
        ECHO %comfyui_install_dir%
        SHIFT
    ) ELSE (
        ECHO "An existing directory MUST be provided when using the -i command line option. Install will exit."
        GOTO :END
    )
)
IF /I "%1"=="--installFolder" (
    ECHO Custom ComfyUI Path provided:
    IF EXIST "%2" (
        IF "%2:~-1%" NEQ "\" (
            set "comfyui_install_dir=%2\"
        ) ELSE (
            set "comfyui_install_dir=%2"
        )
        ECHO %comfyui_install_dir%
        SHIFT
    ) ELSE (
        ECHO "An existing directory MUST be provided when using the -i command line option. Install will exit."
        GOTO :END
    )
)
shift
GOTO :ProcessArg

:SetManifest
SET manifestFile=%1
SET "customManifest=True"

:CheckExistingComfyInstall
IF EXIST %comfyui_install_dir%comfyui (
    GOTO :GetUserInput
)
IF EXIST %comfyui_install_dir%ComfyUI_windows_portable\comfyui (
    SET "comfyui_install_dir=%comfyui_install_dir%ComfyUI_windows_portable\"
    GOTO :GetUserInput
)
GOTO :StartInstall

:GetUserInput
ECHO An existing ComfyUI installation was found in this directory. How would you like to proceed?
ECHO 1. Resume Installation 
ECHO 0. Exit
SET /P choice="Enter your choice (1 or 0): "
ECHO Option %choice% was selected
IF "%choice%"=="1" (
    ECHO Installing component files only
    GOTO :InstallGit
) ELSE IF "%choice%"=="0" (
    GOTO :END
) ELSE (
    ECHO Invalid Selection!!!!
    ECHO Please select a valid option...
    GOTO :CheckExistingComfyInstall
)

:StartInstall
ECHO Download ComfyUI
curl -OL https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z
IF %ERRORLEVEL% NEQ 0 (
    ECHO Problem with file download, try again
    EXIT
) ELSE (
    ECHO Extract ComfyUI
    IF "%comfyui_install_dir%"==".\ComfyUI_windows_portable\" (
        tar -xvf .\ComfyUI_windows_portable_nvidia.7z
    ) ELSE (
        mkdir %comfyui_install_dir% 2>nul
        pushd %comfyui_install_dir%
        tar -xvf ..\ComfyUI_windows_portable_nvidia.7z
        popd
        SET "comfyui_install_dir=%comfyui_install_dir%\ComfyUI_windows_portable\"
    )
    echo The current directory is: %CD%
    GOTO :InstallGit
)

:InstallGit
where git.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Git is already installed and found in PATH.
    goto :InstallPythonPackages
)
echo Git not found in PATH. Installing Git...
winget install --id Git.Git --silent --disable-interactivity
if %ERRORLEVEL% neq 0 (
    echo Failed to install Git using winget.
    exit /b 1
)
set "GIT_DEFAULT_PATH=%ProgramFiles%\Git\cmd\git.exe"
if exist "%GIT_DEFAULT_PATH%" (
    echo Git found at %GIT_DEFAULT_PATH%.
    set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
    echo Added %ProgramFiles%\Git\cmd to the current PATH.
) else (
    echo Git was installed but not found at %GIT_DEFAULT_PATH%.
    exit /b 1
)

:InstallPythonPackages
ECHO Install the Python Dependencies
ECHO "%comfyui_install_dir%python_embeded\python.exe" -m pip install --no-cache-dir requests gitpython py7zr huggingface-hub validators
"%comfyui_install_dir%python_embeded\python.exe" -s -m pip install --upgrade pip
"%comfyui_install_dir%python_embeded\python.exe" -m pip install --no-cache-dir requests gitpython huggingface-hub validators pynvml

ECHO Download the Rest of the content
ECHO "%comfyui_install_dir%python_embeded\python.exe" -s .\installmill.py %* --baseFolder "%base_dir%" --installFolder "%comfyui_install_dir%"
start cmd /k "pushd "%~dp0" && "%comfyui_install_dir%python_embeded\python.exe" -s .\installmill.py %* --baseFolder "%base_dir%" --installFolder "%comfyui_install_dir%"

:END
pause
endlocal