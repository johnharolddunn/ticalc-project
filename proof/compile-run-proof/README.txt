Proof of TiCalc PC file access run - 15 Nov 2026
Program : stats.txt (TI-Basic) compiled to stats.exe by tibasic_compiler.py
Input   : TempData.txt (3000 values, chosen via pickfile() dialog)
Output  : TempData.txt.stats.txt (written by WriteLines)
Check   : count/sum/mean verified independently in PowerShell (n=3000, sum=313348.39, mean=104.4495);
          median/stdev verified against Python's statistics module.
