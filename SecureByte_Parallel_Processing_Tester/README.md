1. I have tested two types of processing for code analysis. One is Parallel Chunk Processing and the other the usual Sequential Processing. 

2. The former is to speed-up the process of analysing big amounts of code by chunking the code into logical pieces. 

3. My test file is in the folder "test_files" and all of my code currently works to test "test_1.py" only. You'd have to change a few lines in the "parallel_chunk_processor.py" to make the processing dyanmic for any file provided.

4. The "run_comparison.bat" file was made solely to test the speed of both the methods in my Windows Terminal. As expected, the "parallel_chunk_processor.py" ran faster than its counterpart. It produced good security reviews as well.

5. You can run each .py file to see what its output is. You can run the .bat file to compare the times!