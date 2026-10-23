const SPREADSHEET_ID = '1LH8vtd84Ahpsu2uErW-RVW1XOxMp5lMLRGmoJtGC-9Y';
const SHEET_NAME = 'Sheet1';
const HEADERS = ['username', 'id_pesanan', 'nomor_resi', 'tanggal_kirim', 'status_pengiriman'];

function ensureHeaders(sheet) {
  const values = sheet.getDataRange().getValues();
  if (!values.length || values[0].some((cell) => String(cell || '').trim() !== '')) {
    const firstRow = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
    if (firstRow.every((cell) => String(cell || '').trim() === '')) {
      sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    } else if (!firstRow.every((cell, index) => String(cell || '').trim() === HEADERS[index])) {
      sheet.insertRowBefore(1);
      sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    }
  }
}

function doGet() {
  return ContentService.createTextOutput(JSON.stringify({ ok: true, spreadsheetId: SPREADSHEET_ID, sheetName: SHEET_NAME }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents || '{}');
    const rows = Array.isArray(payload.rows) ? payload.rows : [];

    if (!rows.length) {
      return ContentService.createTextOutput(JSON.stringify({ ok: false, message: 'No rows to append.' }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = spreadsheet.getSheetByName(SHEET_NAME) || spreadsheet.insertSheet(SHEET_NAME);

    ensureHeaders(sheet);

    const normalizedRows = rows.map((row) => [
      row.username || '',
      row.id_pesanan || '',
      row.nomor_resi || '',
      row.tanggal_kirim || '',
      row.status_pengiriman || ''
    ]);

    sheet.getRange(sheet.getLastRow() + 1, 1, normalizedRows.length, HEADERS.length).setValues(normalizedRows);

    return ContentService.createTextOutput(JSON.stringify({ ok: true, inserted: normalizedRows.length }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, message: error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
