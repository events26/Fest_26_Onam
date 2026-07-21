/**********************************************************************
 *  CAFS Onam 2026 — Admin Console backend (Google Apps Script)
 *
 *  Powers register.html: participant registration, match/result
 *  management, and team points — all written into the SAME Google Sheet
 *  the main page reads from. Admin password is checked SERVER-SIDE.
 *
 *  SETUP (one time)
 *   1. Open your Google Sheet -> Extensions -> Apps Script.
 *   2. Delete sample code, paste ALL of this file.
 *   3. Set SHEET_ID below (from the sheet URL:
 *        docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit ).
 *   4. Deploy -> New deployment -> Web app -> Execute as: Me,
 *      Who has access: Anyone -> Deploy -> authorise -> copy the /exec URL.
 *   5. Paste that URL into register.html AND index.html (CONFIG.SCRIPT_URL
 *      is only needed by register.html; index.html reads via SHEET_ID).
 *
 *  Changing code later: Deploy -> Manage deployments -> edit ->
 *  Version: New version -> Deploy (keeps the same URL).
 **********************************************************************/

const SHEET_ID = 'PASTE_YOUR_SHEET_ID_HERE';

const TAB_PART    = 'Participants';
const TAB_MATCH   = 'Matches';
const TAB_TEAMS   = 'Teams & Scores';

// SET YOUR REAL PASSWORD HERE inside the Apps Script editor in Google ONLY.
// Do NOT commit the real password to the repo. Pick a fresh, strong one.
const ADMINS = { 'admin': 'REPLACE_WITH_A_STRONG_PASSWORD' };   // server-side only

const PART_HEAD  = ['ID','Timestamp','Event','Name','Department','Phone','Team','Gender','Notes','AddedBy'];
const MATCH_HEAD = ['ID','Event','TeamA','TeamB','Status','ScoreA','ScoreB','Winner','Note'];
const TEAM_HEAD  = ['Team','Captain','Vice Captain','Total Points'];
const TAB_GALLERY = 'Gallery';
const GALLERY_HEAD = ['ID','Timestamp','FileId','Caption','AddedBy'];
const GALLERY_FOLDER_NAME = 'CAFS Onam Gallery';   // Drive folder auto-created for photos

function doGet(e)  { return handle({ action: 'all' }); }
function doPost(e) {
  var d = {}; try { d = JSON.parse(e.postData.contents); } catch (err) {}
  return handle(d);
}

function handle(d) {
  var out;
  try {
    var a = (d && d.action) || 'all';
    if (a === 'all')        out = { ok: true, teams: listTeams(), participants: listParts(), matches: listMatches(), gallery: listGallery() };
    else if (a === 'auth')  out = { ok: valid(d.user, d.pass), error: 'Invalid username or password' };
    else if (a === 'list')  out = { ok: true, rows: listParts() };
    else if (a === 'add')      out = need(d) || (addPart(d.p || {}, d.user),       { ok: true, participants: listParts() });
    else if (a === 'delete')   out = need(d) || (delPart(d.rowId),                  { ok: true, participants: listParts() });
    else if (a === 'saveMatch')out = need(d) || (saveMatch(d.m || {}),              { ok: true, matches: listMatches() });
    else if (a === 'delMatch') out = need(d) || (delMatch(d.rowId),                 { ok: true, matches: listMatches() });
    else if (a === 'saveTeams')out = need(d) || (saveTeams(d.teams || []),          { ok: true, teams: listTeams() });
    else if (a === 'uploadPhoto') out = need(d) || (uploadPhoto(d.p || {}, d.user),  { ok: true, gallery: listGallery() });
    else if (a === 'delPhoto')    out = need(d) || (delPhoto(d.rowId),               { ok: true, gallery: listGallery() });
    else out = { ok: false, error: 'Unknown action' };
  } catch (err) { out = { ok: false, error: String(err) }; }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

function valid(u, p) { return !!u && ADMINS.hasOwnProperty(u) && ADMINS[u] === p; }
function need(d) { return valid(d.user, d.pass) ? null : { ok: false, error: 'Invalid login' }; }

function ss() { return SpreadsheetApp.openById(SHEET_ID); }
function tab(name, head) {
  var s = ss().getSheetByName(name);
  if (!s) s = ss().insertSheet(name);
  if (s.getLastRow() === 0) s.appendRow(head);
  return s;
}

/* ---------- participants ---------- */
function listParts() {
  var s = tab(TAB_PART, PART_HEAD), last = s.getLastRow(); if (last < 2) return [];
  return s.getRange(2, 1, last - 1, PART_HEAD.length).getValues()
    .filter(function (r) { return r[0] !== ''; })
    .map(function (r) { return { id:r[0],ts:r[1],event:r[2],name:r[3],dept:r[4],phone:r[5],team:r[6],gender:r[7],notes:r[8],addedBy:r[9] }; });
}
function addPart(p, user) {
  var s = tab(TAB_PART, PART_HEAD);
  var ts = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  s.appendRow(['P'+(new Date().getTime()), ts, p.event||'', p.name||'', p.dept||'', p.phone||'', p.team||'', p.gender||'', p.notes||'', user||'']);
}
function delPart(id) { deleteById(tab(TAB_PART, PART_HEAD), id); }

/* ---------- matches ---------- */
function listMatches() {
  var s = tab(TAB_MATCH, MATCH_HEAD), last = s.getLastRow(); if (last < 2) return [];
  return s.getRange(2, 1, last - 1, MATCH_HEAD.length).getValues()
    .filter(function (r) { return r[0] !== ''; })
    .map(function (r) { return { id:r[0],event:r[1],teamA:r[2],teamB:r[3],status:r[4],scoreA:r[5],scoreB:r[6],winner:r[7],note:r[8] }; });
}
function saveMatch(m) {
  var s = tab(TAB_MATCH, MATCH_HEAD), last = s.getLastRow();
  var row = [m.id, m.event||'', m.teamA||'', m.teamB||'', m.status||'Scheduled', m.scoreA||'', m.scoreB||'', m.winner||'', m.note||''];
  if (m.id && last >= 2) {
    var ids = s.getRange(2, 1, last - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) if (ids[i][0] === m.id) { s.getRange(i+2, 1, 1, MATCH_HEAD.length).setValues([row]); return; }
  }
  row[0] = 'M' + (new Date().getTime());
  s.appendRow(row);
}
function delMatch(id) { deleteById(tab(TAB_MATCH, MATCH_HEAD), id); }

/* ---------- teams ---------- */
function listTeams() {
  var s = tab(TAB_TEAMS, TEAM_HEAD), last = s.getLastRow(); if (last < 2) return [];
  return s.getRange(2, 1, last - 1, TEAM_HEAD.length).getValues()
    .filter(function (r) { return r[0] !== ''; })
    .map(function (r) { return { name:r[0], cap:r[1], vc:r[2], points:r[3] }; });
}
function saveTeams(teams) {
  var s = tab(TAB_TEAMS, TEAM_HEAD), last = s.getLastRow();
  if (last >= 2) s.getRange(2, 1, last - 1, TEAM_HEAD.length).clearContent();
  if (!teams.length) return;
  var rows = teams.map(function (t) { return [t.name||'', t.cap||'', t.vc||'', (t.points!=null?t.points:0)]; });
  s.getRange(2, 1, rows.length, TEAM_HEAD.length).setValues(rows);
}

/* ---------- gallery (photos stored in a Drive folder) ---------- */
function galleryFolder() {
  var it = DriveApp.getFoldersByName(GALLERY_FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(GALLERY_FOLDER_NAME);
}
function listGallery() {
  var s = tab(TAB_GALLERY, GALLERY_HEAD), last = s.getLastRow(); if (last < 2) return [];
  return s.getRange(2, 1, last - 1, GALLERY_HEAD.length).getValues()
    .filter(function (r) { return r[0] !== ''; })
    .map(function (r) { return { id:r[0], ts:r[1], fileId:r[2], caption:r[3], addedBy:r[4] }; });
}
function uploadPhoto(p, user) {
  var bytes = Utilities.base64Decode(p.data);
  var blob = Utilities.newBlob(bytes, p.mime || 'image/jpeg', p.name || ('photo_' + (new Date().getTime()) + '.jpg'));
  var file = galleryFolder().createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  var s = tab(TAB_GALLERY, GALLERY_HEAD);
  var ts = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  s.appendRow(['G' + (new Date().getTime()), ts, file.getId(), p.caption || '', user || '']);
}
function delPhoto(id) {
  var s = tab(TAB_GALLERY, GALLERY_HEAD), last = s.getLastRow(); if (last < 2) return;
  var vals = s.getRange(2, 1, last - 1, GALLERY_HEAD.length).getValues();
  for (var i = 0; i < vals.length; i++) if (vals[i][0] === id) {
    try { DriveApp.getFileById(vals[i][2]).setTrashed(true); } catch (e) {}
    s.deleteRow(i + 2); return;
  }
}

/* ---------- shared ---------- */
function deleteById(s, id) {
  var last = s.getLastRow(); if (last < 2) return;
  var ids = s.getRange(2, 1, last - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) if (ids[i][0] === id) { s.deleteRow(i + 2); return; }
}
