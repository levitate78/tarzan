import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { TeamDashboardPage } from "./pages/TeamDashboardPage";
import { MemberDashboardPage } from "./pages/MemberDashboardPage";
import { IssuesPage } from "./pages/IssuesPage";
import { MergeRequestsPage } from "./pages/MergeRequestsPage";
import { SkillsMatrixPage } from "./pages/SkillsMatrixPage";
import { ProfilePage } from "./pages/ProfilePage";
import { TeamPage } from "./pages/TeamPage";
import { SkillsAdminPage } from "./pages/SkillsAdminPage";
import { ConnectorsAdminPage } from "./pages/ConnectorsAdminPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<TeamDashboardPage />} />
        <Route path="issues" element={<IssuesPage />} />
        <Route path="merge-requests" element={<MergeRequestsPage />} />
        <Route path="skills" element={<SkillsMatrixPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="team/:userId" element={<MemberDashboardPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route
          path="admin/skills"
          element={
            <ProtectedRoute requiredRole="admin">
              <SkillsAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/connectors"
          element={
            <ProtectedRoute requiredRole="admin">
              <ConnectorsAdminPage />
            </ProtectedRoute>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
