import { useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Link from "@mui/material/Link";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { useImportSkillLevels } from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import type { SkillsImportResult } from "../api/types";

const TEMPLATE_CSV =
  "username,skill,level,aspiration_level,category\n" +
  "alice,Python,4,5,languages\n" +
  "bob,Terraform,2,3,devops\n";

const MAX_FILE_BYTES = 1_000_000;

export function SkillsImportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const importSkills = useImportSkillLevels();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [csvContent, setCsvContent] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [result, setResult] = useState<SkillsImportResult | null>(null);

  const handleClose = () => {
    setFileName(null);
    setCsvContent(null);
    setFileError(null);
    setResult(null);
    importSkills.reset();
    onClose();
  };

  const handleFileSelected = async (file: File | undefined) => {
    setResult(null);
    setFileError(null);
    importSkills.reset();
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setFileError("File is too large (max 1 MB).");
      setFileName(null);
      setCsvContent(null);
      return;
    }
    setFileName(file.name);
    setCsvContent(await file.text());
  };

  const handleImport = async () => {
    if (!csvContent) return;
    try {
      setResult(await importSkills.mutateAsync({ csv_content: csvContent }));
    } catch {
      // error rendered inline
    }
  };

  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "skill-levels-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Import skill levels from CSV</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Upload a CSV with a header row of{" "}
            <code>username,skill,level,aspiration_level,category</code>.{" "}
            <code>aspiration_level</code> and <code>category</code> are optional; levels are 0–5 or
            names (None, Beginner, Elementary, Intermediate, Advanced, Expert).
            Skills not yet in the catalogue are created when a category is given. Existing levels
            for the same member and skill are updated, so re-importing a corrected file is safe.{" "}
            <Link component="button" type="button" onClick={downloadTemplate}>
              Download template
            </Link>
          </Typography>

          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Button variant="outlined" startIcon={<UploadFileIcon />} onClick={() => fileInputRef.current?.click()}>
              Choose file
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              hidden
              aria-label="Skill levels CSV file"
              onChange={(e) => {
                void handleFileSelected(e.target.files?.[0]);
                e.target.value = ""; // allow re-selecting the same file
              }}
            />
            <Typography variant="body2">{fileName ?? "No file selected"}</Typography>
          </Box>

          {!!fileError && <Alert severity="error">{fileError}</Alert>}
          {importSkills.isError && <Alert severity="error">{extractErrorMessage(importSkills.error)}</Alert>}

          {result && (
            <>
              <Alert severity={result.errors.length ? "warning" : "success"}>
                Imported {result.imported_rows} of {result.total_rows} rows: {result.levels_created}{" "}
                skill levels created, {result.levels_updated} updated
                {result.skills_created > 0 && `, ${result.skills_created} new skills added`}
                {result.errors.length > 0 && `. ${result.errors.length} rows were skipped (see below).`}
              </Alert>
              {result.errors.length > 0 && (
                <TableContainer sx={{ maxHeight: 240 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>Line</TableCell>
                        <TableCell>Problem</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {result.errors.map((err) => (
                        <TableRow key={`${err.line}-${err.message}`}>
                          <TableCell>{err.line}</TableCell>
                          <TableCell>{err.message}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>{result ? "Close" : "Cancel"}</Button>
        <Button
          variant="contained"
          disabled={!csvContent || importSkills.isPending}
          onClick={() => void handleImport()}
        >
          {importSkills.isPending ? "Importing…" : "Import"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
