import { createTheme } from "@mui/material/styles";

// A calm, slightly "jungle" palette (deep greens + warm amber accents) that
// avoids the default MUI blue while staying readable for dashboards.
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#2f6f4f",
      dark: "#1f4d36",
      light: "#5b9778",
      contrastText: "#ffffff",
    },
    secondary: {
      main: "#d98e3f",
      contrastText: "#ffffff",
    },
    background: {
      default: "#f4f6f4",
      paper: "#ffffff",
    },
    error: {
      main: "#c0392b",
    },
    warning: {
      main: "#d98e3f",
    },
    success: {
      main: "#2f6f4f",
    },
  },
  shape: {
    borderRadius: 10,
  },
  typography: {
    fontFamily: '"Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "#1f4d36",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid rgba(0,0,0,0.06)",
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 700,
          backgroundColor: "#eef3ef",
        },
      },
    },
  },
});
