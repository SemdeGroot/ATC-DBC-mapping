Attribute VB_Name = "Hergroeperen"
' Hergroepeert de ziektebeeld-tabbladen op basis van de kolom "correctie" in het
' tabblad "Medicatie" van dbc_drugs.xlsx.
'
' Per rij in "Medicatie" geldt: het effectieve ziektebeeld is de waarde in "correctie"
' als die is ingevuld, anders het oorspronkelijke voorstel. "geen" = het middel valt
' uit alle ziektebeeld-tabbladen.
'
' Gebruik (eenmalig importeren, daarna zo vaak draaien als nodig):
'   1. Open dbc_drugs.xlsx in Excel.
'   2. Alt+F11 -> Bestand -> Bestand importeren -> kies dit .bas-bestand.
'   3. Alt+F8 -> HergroepeerZiektebeelden -> Uitvoeren.
'   4. Opslaan als .xlsm als je de macro wilt bewaren.
Option Explicit

Sub HergroepeerZiektebeelden()
    Dim med As Worksheet, ws As Worksheet
    Dim r As Long, lastRow As Long, hdr As Long, outRow As Long
    Dim eff As String

    Set med = ThisWorkbook.Sheets("Medicatie")
    lastRow = med.Cells(med.Rows.Count, 1).End(xlUp).Row

    Application.ScreenUpdating = False
    For Each ws In ThisWorkbook.Worksheets
        If ws.Name <> "Medicatie" Then
            ' Zoek de medicatie-koprij ("atc7" in kolom A) op het ziektebeeld-tabblad.
            hdr = 0
            For r = 1 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
                If LCase(Trim(ws.Cells(r, 1).Value)) = "atc7" Then hdr = r: Exit For
            Next r

            If hdr > 0 Then
                ' Wis de oude medicatielijst onder de koprij.
                With ws.Range(ws.Rows(hdr + 1), ws.Rows(ws.Rows.Count))
                    .ClearContents
                    .Interior.ColorIndex = xlNone
                End With
                outRow = hdr + 1

                ' Vul opnieuw uit "Medicatie" voor dit ziektebeeld.
                For r = 2 To lastRow
                    eff = Trim(med.Cells(r, "K").Value)               ' correctie
                    If eff = "" Then eff = Trim(med.Cells(r, "A").Value)   ' anders het voorstel
                    If LCase(eff) = LCase(ws.Name) Then
                        ws.Cells(outRow, 1).Value = med.Cells(r, "B").Value   ' atc7
                        ws.Cells(outRow, 2).Value = med.Cells(r, "C").Value   ' stofnaam
                        ws.Cells(outRow, 3).Value = med.Cells(r, "D").Value   ' categorie
                        ws.Cells(outRow, 4).Value = med.Cells(r, "E").Value   ' off_label
                        ws.Cells(outRow, 5).Value = med.Cells(r, "F").Value   ' zekerheid
                        ws.Cells(outRow, 6).Value = med.Cells(r, "G").Value   ' methode
                        If LCase(Trim(med.Cells(r, "E").Value)) = "ja" Then
                            ws.Range(ws.Cells(outRow, 1), ws.Cells(outRow, 6)).Interior.Color = RGB(255, 242, 168)
                        End If
                        outRow = outRow + 1
                    End If
                Next r
            End If
        End If
    Next ws
    Application.ScreenUpdating = True
    MsgBox "Ziektebeeld-tabbladen bijgewerkt op basis van de kolom 'correctie'.", vbInformation
End Sub
