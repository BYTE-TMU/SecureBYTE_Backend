@echo off
REM This script runs both analysis methods and times them.

REM This is the test file you are using.
REM <<<<<<< IMPORTANT: UPDATE THIS PATH >>>>>>>
REM This now defaults to test_1.py, but you can change it to your 2k-line file!
set TEST_FILE="test_files\test_1.py"
REM Note: Windows uses backslashes \ for paths

echo ==========================================================
echo Starting Comparison Test...
echo Analyzing file: %TEST_FILE%
echo ==========================================================

echo.
echo --- TEST 1: SEQUENTIAL (One Big Call) ---
echo Running 'python sequential_analyser.py -f %TEST_FILE%'...
echo.

REM Use PowerShell's Measure-Command to get the execution time
powershell -Command "Measure-Command { python sequential_analyser.py -f %TEST_FILE% }"

echo.
echo ==========================================================
echo.
echo --- TEST 2: PARALLEL (Multiple Chunks) ---
echo Running 'python parallel_chunk_processor.py -f %TEST_FILE%'...
echo.

REM Use PowerShell's Measure-Command to get the execution time
powershell -Command "Measure-Command { python parallel_chunk_processor.py -f %TEST_FILE% }"

echo.
echo ==========================================================
echo Comparison Complete.
echo Check the 'TotalSeconds' for both tests.
echo ==========================================================