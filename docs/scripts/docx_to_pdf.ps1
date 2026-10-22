# docx_to_pdf.ps1 - Export a review Word document to PDF using Microsoft Word itself.
# Run from the repository root:   powershell -ExecutionPolicy Bypass -File docs/scripts/docx_to_pdf.ps1 [path.docx]
# With no argument it exports the Review 3 document.
param([string]$Path = "docs/Review_3_Testing_Evaluation_and_Results.docx")
$docx = (Resolve-Path $Path).Path
$pdf = [IO.Path]::ChangeExtension($docx, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($docx, $false, $true)
    $doc.ExportAsFixedFormat($pdf, 17)   # 17 = wdExportFormatPDF
    $doc.Close($false)
    Write-Output "written $pdf"
} finally {
    $word.Quit()
}
