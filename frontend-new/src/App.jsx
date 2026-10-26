import { Fragment, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Bot,
  Camera,
  CheckCircle,
  ChevronRight,
  Clock,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Shield,
  ShieldAlert,
  Settings,
  Siren,
  User,
  X,
  Upload,
  Video,
  RefreshCw,
  Eye,
  Users,
} from "lucide-react";

import {
  apiRequest,
  fetchAttachmentBlob,
  login,
  logout,
  handleUnauthorizedSession,
  API_URL,
} from "./api";

import "./App.css";


/* =========================
   COMMON HELPERS
========================= */

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("campusguard_user")) || null;
  } catch {
    return null;
  }
}

function formatDate(value) {
  if (!value) return "-";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function getSeverityClass(value) {
  const text = String(value || "").toLowerCase();

  if (text === "high" || text === "critical") {
    return "status-danger";
  }

  if (text === "medium" || text === "caution") {
    return "status-warning";
  }

  if (text === "low" || text === "normal") {
    return "status-success";
  }

  return "status-neutral";
}


/* =========================
   ROUTING & APP
========================= */
const ALLOWED_PAGES_BY_ROLE = {
  student: ["dashboard", "incidents", "sos", "assistant"],
  security: ["dashboard", "alerts", "incidents", "cctv", "analytics", "assistant"],
  admin: ["dashboard", "alerts", "incidents", "cctv", "analytics", "assistant", "settings"],
};

function getSafeInitialPage(userRole) {
  if (typeof window !== "undefined") {
    const hash = window.location.hash.replace("#", "").toLowerCase();
    const role = String(userRole || "").toLowerCase();
    const allowed = ALLOWED_PAGES_BY_ROLE[role] || ["dashboard"];
    if (hash && allowed.includes(hash)) {
      return hash;
    }
  }
  return "dashboard";
}

export default function App() {
  const [user, setUser] = useState(getStoredUser());
  const role = String(user?.role || "").toLowerCase();
  const allowedPages = ALLOWED_PAGES_BY_ROLE[role] || ["dashboard"];
  const [activePage, setActivePageState] = useState(() => getSafeInitialPage(role));
  const [mobileMenu, setMobileMenu] = useState(false);

  const setActivePage = (page) => {
    const target = allowedPages.includes(page) ? page : "dashboard";
    setActivePageState(target);
    if (typeof window !== "undefined") {
      window.location.hash = target;
    }
  };

  useEffect(() => {
    function handleSessionExpired() {
      setUser(null);
      setActivePage("dashboard");
    }

    function handleHashChange() {
      if (!user) return;
      const hash = window.location.hash.replace("#", "").toLowerCase();
      if (hash) {
        if (allowedPages.includes(hash)) {
          setActivePageState(hash);
        } else {
          setActivePageState("dashboard");
          window.location.hash = "dashboard";
        }
      }
    }

    window.addEventListener("campusguard_auth_expired", handleSessionExpired);
    window.addEventListener("hashchange", handleHashChange);
    return () => {
      window.removeEventListener("campusguard_auth_expired", handleSessionExpired);
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, [user, allowedPages]);

  function handleLogin(data) {
    const loggedInRole = String(data.role || "").toLowerCase();
    setUser({
      user_id: data.user_id,
      name: data.name,
      email: data.email,
      role: data.role,
    });

    const initial = getSafeInitialPage(loggedInRole);
    setActivePageState(initial);
    if (typeof window !== "undefined") {
      window.location.hash = initial;
    }
  }

  function handleLogout() {
    logout();
    setUser(null);
    setActivePageState("dashboard");
    if (typeof window !== "undefined") {
      window.location.hash = "dashboard";
    }
  }

  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  const closeMobileMenu = () => {
    setMobileMenu(false);
  };

  return (
    <div className="app-shell">

      <Sidebar
        user={user}
        activePage={activePage}
        setActivePage={setActivePage}
        onLogout={handleLogout}
        mobileMenu={mobileMenu}
        closeMobileMenu={closeMobileMenu}
      />

      {mobileMenu && (
        <div
          className="mobile-overlay"
          onClick={closeMobileMenu}
        />
      )}

      <main className="main-content">

        <header className="topbar">

          <div className="topbar-left">

            <button
              className="mobile-menu-button"
              onClick={() => setMobileMenu(true)}
            >
              <Menu size={22} />
            </button>

            <div>
              <div className="topbar-title">
                {getPageTitle(activePage, role)}
              </div>

              <div className="topbar-subtitle">
                CampusGuard AI Security Intelligence
              </div>
            </div>

          </div>

          <div className="topbar-right">

            <div className="system-status">
              <span className="status-dot online" />
              System Online
            </div>

            <div className="user-mini">

              <div className="avatar">
                {user.name?.charAt(0)?.toUpperCase() || "U"}
              </div>

              <div className="user-mini-info">
                <strong>{user.name}</strong>
                <span>{capitalize(role)}</span>
              </div>

            </div>

          </div>

        </header>


        <div className="page-container">

          {activePage === "dashboard" && (
            role === "student" ? (
              <StudentDashboard
                user={user}
                setActivePage={setActivePage}
              />
            ) : role === "security" ? (
              <SecurityDashboard
                setActivePage={setActivePage}
              />
            ) : (
              <AdminDashboard
                setActivePage={setActivePage}
              />
            )
          )}

          {activePage === "incidents" && (
            <IncidentsPage user={user} />
          )}

          {activePage === "cctv" && (role === "admin" || role === "security") && (
            <CCTVPage />
          )}

          {activePage === "alerts" && (role === "admin" || role === "security") && (
            <AlertsPage />
          )}

          {activePage === "analytics" && (role === "admin" || role === "security") && (
            <AnalyticsPage />
          )}

          {activePage === "assistant" && (
            <AssistantPage />
          )}

          {activePage === "settings" && role === "admin" && (
            <SettingsPage user={user} />
          )}

          {activePage === "sos" && role === "student" && (
            <SOSPage />
          )}

        </div>

      </main>

    </div>
  );
}


/* =========================
   LOGIN
========================= */

function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");

    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }

    try {
      setLoading(true);

      const data = await login(email, password);

      onLogin(data);

    } catch (err) {
      setError(err.message || "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">

      <section className="login-brand-panel">

        <div className="brand-logo large">
          <Shield size={30} />
        </div>

        <div className="brand-name large-brand">
          CampusGuard AI
        </div>

        <h1>
          AI-Powered Campus Safety Intelligence
        </h1>

        <p>
          Multi-signal risk prediction, intelligent alerts,
          CCTV analysis and AI-assisted campus safety management.
        </p>

        <div className="login-feature-list">

          <div>
            <CheckCircle size={18} />
            <span>Real-time safety monitoring</span>
          </div>

          <div>
            <CheckCircle size={18} />
            <span>AI-powered threat detection</span>
          </div>

          <div>
            <CheckCircle size={18} />
            <span>Centralized security intelligence</span>
          </div>

        </div>

      </section>


      <section className="login-form-panel">

        <div className="login-card">

          <div className="login-mobile-logo">
            <div className="brand-logo">
              <Shield size={24} />
            </div>
            <strong>CampusGuard AI</strong>
          </div>

          <div className="login-heading">
            <h2>Welcome back</h2>
            <p>
              Sign in to access your campus safety dashboard.
            </p>
          </div>

          <form onSubmit={handleSubmit}>

            <label>Email</label>

            <div className="input-with-icon">
              <User size={18} />
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="Enter your email"
              />
            </div>


            <label>Password</label>

            <div className="input-with-icon">
              <Shield size={18} />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
              />
            </div>


            {error && (
              <div className="error-message">
                <AlertTriangle size={17} />
                {error}
              </div>
            )}


            <button
              className="primary-button login-button"
              type="submit"
              disabled={loading}
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>

          </form>

          <div className="login-quick-demo">
            <span>Quick Demo Roles:</span>
            <div className="demo-buttons-row">
              <button
                type="button"
                className="demo-role-btn"
                onClick={() => {
                  setEmail("student@campusguard.com");
                  setPassword("Student@123");
                  setError("");
                }}
              >
                Student
              </button>
              <button
                type="button"
                className="demo-role-btn"
                onClick={() => {
                  setEmail("security@campusguard.com");
                  setPassword("Security@123");
                  setError("");
                }}
              >
                Security
              </button>
              <button
                type="button"
                className="demo-role-btn"
                onClick={() => {
                  setEmail("admin@campusguard.com");
                  setPassword("Admin@123");
                  setError("");
                }}
              >
                Admin
              </button>
            </div>
          </div>

          <div className="login-security-note">
            <Shield size={15} />
            Secure authenticated access
          </div>

        </div>

      </section>

    </div>
  );
}


/* =========================
   SIDEBAR
========================= */

function Sidebar({
  user,
  activePage,
  setActivePage,
  onLogout,
  mobileMenu,
  closeMobileMenu,
}) {
  const role = String(user.role || "").toLowerCase();

  let navigation = [];

  if (role === "student") {
    navigation = [
      {
        label: "Dashboard",
        icon: LayoutDashboard,
        page: "dashboard",
      },
      {
        label: "My Incidents",
        icon: FileText,
        page: "incidents",
      },
      {
        label: "Emergency SOS",
        icon: Siren,
        page: "sos",
      },
      {
        label: "AI Assistant",
        icon: Bot,
        page: "assistant",
      },
    ];
  }

  if (role === "security") {
    navigation = [
      {
        label: "Dashboard",
        icon: LayoutDashboard,
        page: "dashboard",
      },
      {
        label: "Alerts",
        icon: Bell,
        page: "alerts",
      },
      {
        label: "Incidents",
        icon: FileText,
        page: "incidents",
      },
      {
        label: "CCTV Intelligence",
        icon: Camera,
        page: "cctv",
      },
      {
        label: "Analytics",
        icon: BarChart3,
        page: "analytics",
      },
      {
        label: "AI Assistant",
        icon: Bot,
        page: "assistant",
      },
    ];
  }

  if (role === "admin") {
    navigation = [
      {
        label: "Dashboard",
        icon: LayoutDashboard,
        page: "dashboard",
      },
      {
        label: "Alerts",
        icon: Bell,
        page: "alerts",
      },
      {
        label: "Incidents",
        icon: FileText,
        page: "incidents",
      },
      {
        label: "CCTV Intelligence",
        icon: Camera,
        page: "cctv",
      },
      {
        label: "Analytics",
        icon: BarChart3,
        page: "analytics",
      },
      {
        label: "AI Assistant",
        icon: Bot,
        page: "assistant",
      },
      {
        label: "Settings",
        icon: Settings,
        page: "settings",
      },
    ];
  }

  return (
    <aside className={`sidebar ${mobileMenu ? "sidebar-open" : ""}`}>

      <div className="sidebar-header">

        <div className="brand-logo">
          <Shield size={23} />
        </div>

        <div className="brand-text">
          <strong>CampusGuard</strong>
          <span>AI Safety Platform</span>
        </div>

        <button
          className="mobile-close-button"
          onClick={closeMobileMenu}
        >
          <X size={20} />
        </button>

      </div>


      <div className="sidebar-section-title">
        Navigation
      </div>

      <nav className="sidebar-nav">

        {navigation.map((item) => {

          const Icon = item.icon;

          return (
            <button
              key={item.page}
              className={`nav-item ${
                activePage === item.page ? "active" : ""
              }`}
              onClick={() => {
                setActivePage(item.page);
                closeMobileMenu();
              }}
            >
              <Icon size={19} />
              <span>{item.label}</span>

              {activePage === item.page && (
                <ChevronRight
                  className="nav-chevron"
                  size={16}
                />
              )}
            </button>
          );

        })}

      </nav>


      <div className="sidebar-bottom">

        <div className="sidebar-user">

          <div className="avatar">
            {user.name?.charAt(0)?.toUpperCase() || "U"}
          </div>

          <div>
            <strong>{user.name}</strong>
            <span>{capitalize(role)}</span>
          </div>

        </div>


        <button
          className="logout-button"
          onClick={onLogout}
        >
          <LogOut size={18} />
          Logout
        </button>

      </div>

    </aside>
  );
}


/* =========================
   STUDENT DASHBOARD
========================= */

function StudentDashboard({ user, setActivePage }) {
  const [incidents, setIncidents] = useState([]);
  const [sosAlerts, setSosAlerts] = useState([]);

  const [loading, setLoading] = useState(true);
  const [sosLoading, setSosLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [incidentType, setIncidentType] = useState("Suspicious Activity");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadStudentData() {
    try {
      setLoading(true);

      const [incidentData, sosData] = await Promise.all([
        apiRequest("/incidents"),
        apiRequest("/sos"),
      ]);

      setIncidents(Array.isArray(incidentData) ? incidentData : []);
      setSosAlerts(Array.isArray(sosData) ? sosData : []);

    } catch (err) {
      setError(err.message || "Unable to load dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStudentData();
  }, []);

  async function sendSOS() {
    const confirmed = window.confirm(
      "Send an emergency SOS alert to campus security?"
    );

    if (!confirmed) return;

    try {
      setSosLoading(true);
      setMessage("");
      setError("");

      const data = await apiRequest("/sos", {
        method: "POST",
      });

      setMessage(
        data.message || "Emergency SOS alert sent successfully."
      );

      await loadStudentData();

    } catch (err) {
      setError(err.message || "Unable to send SOS.");
    } finally {
      setSosLoading(false);
    }
  }

  async function reportIncident(event) {
    event.preventDefault();

    if (!location || !description) {
      setError("Please enter the location and description.");
      return;
    }

    try {
      setSubmitting(true);
      setMessage("");
      setError("");

      const data = await apiRequest("/incidents", {
        method: "POST",
        body: JSON.stringify({
          incident_type: incidentType,
          location,
          description,
        }),
      });

      setMessage(
        data.message || "Incident reported successfully."
      );

      setLocation("");
      setDescription("");

      await loadStudentData();

    } catch (err) {
      setError(err.message || "Unable to report incident.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleNewReportClick() {
    setLocation("");
    setDescription("");
    setMessage("");
    setError("");
    setTimeout(() => {
      const input = document.getElementById("student-report-location");
      if (input) {
        input.focus();
        input.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 60);
  }

  const activeSosCount = sosAlerts.filter(
    (item) => item.status === "active"
  ).length;

  const recentIncidents = incidents.slice(0, 5);

  return (
    <div className="dashboard-page">

      <div className="page-heading-row">

        <div>
          <h1>Good to see you, {user.name}</h1>
          <p>
            Stay informed and report safety concerns quickly.
          </p>
        </div>

        <button
          className="refresh-button"
          onClick={loadStudentData}
        >
          <RefreshCw size={17} />
          Refresh
        </button>

      </div>


      {message && (
        <div className="success-message">
          <CheckCircle size={18} />
          {message}
        </div>
      )}

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}


      <div className="student-hero">

        <div>
          <div className="eyebrow">
            CAMPUS SAFETY
          </div>

          <h2>
            Your safety matters.
          </h2>

          <p>
            Use the emergency SOS for immediate assistance
            or report a safety concern to campus security.
          </p>
        </div>

        <button
          className="sos-large-button"
          onClick={sendSOS}
          disabled={sosLoading}
        >
          <Siren size={28} />
          <span>
            {sosLoading ? "Sending..." : "EMERGENCY SOS"}
          </span>
          <small>
            Notify campus security
          </small>
        </button>

      </div>


      <div className="stats-grid">

        <StatCard
          title="My Incidents"
          value={incidents.length}
          icon={FileText}
          tone="blue"
        />

        <StatCard
          title="Active SOS"
          value={activeSosCount}
          icon={Siren}
          tone="red"
        />

        <StatCard
          title="Resolved Reports"
          value={
            incidents.filter(
              (item) => item.status === "resolved"
            ).length
          }
          icon={CheckCircle}
          tone="green"
        />

        <StatCard
          title="Account"
          value="Active"
          icon={User}
          tone="slate"
        />

      </div>


      <div className="two-column-grid">

        <section className="panel">

          <PanelHeader
            icon={FileText}
            title="Report an Incident"
            action="New Report"
            onAction={handleNewReportClick}
          />

          <form
            className="incident-form"
            onSubmit={reportIncident}
          >

            <label>Incident Type</label>

            <select
              value={incidentType}
              onChange={(event) =>
                setIncidentType(event.target.value)
              }
            >
              <option>Suspicious Activity</option>
              <option>Harassment</option>
              <option>Fight</option>
              <option>Medical Emergency</option>
              <option>Fire / Smoke</option>
              <option>Theft</option>
              <option>Restricted Area</option>
              <option>Other</option>
            </select>


            <label>Location</label>

            <input
              id="student-report-location"
              value={location}
              onChange={(event) =>
                setLocation(event.target.value)
              }
              placeholder="Example: Block A, 2nd Floor"
            />


            <label>Description</label>

            <textarea
              value={description}
              onChange={(event) =>
                setDescription(event.target.value)
              }
              placeholder="Describe the safety concern..."
              rows="4"
            />


            <button
              className="primary-button"
              type="submit"
              disabled={submitting}
            >
              {submitting ? "Submitting Report..." : "Submit Incident Report"}
            </button>

          </form>

        </section>


        <section className="panel">

          <PanelHeader
            icon={Clock}
            title="Recent Incidents"
            action="View All"
            onAction={() => setActivePage("incidents")}
          />

          {loading ? (
            <LoadingState />
          ) : recentIncidents.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No incidents reported"
              text="Your submitted reports will appear here."
            />
          ) : (
            <div className="activity-list">

              {recentIncidents.map((incident) => (

                <div
                  className="activity-item"
                  key={incident.id}
                >

                  <div className="activity-icon blue-icon">
                    <FileText size={17} />
                  </div>

                  <div className="activity-content">

                    <strong>
                      {incident.incident_type}
                    </strong>

                    <span>
                      {incident.location}
                    </span>

                    <small>
                      {formatDate(incident.created_at)}
                    </small>

                  </div>

                  <StatusBadge
                    value={incident.status}
                  />

                </div>

              ))}

            </div>
          )}

        </section>

      </div>


      <section className="panel">

        <PanelHeader
          icon={Siren}
          title="SOS History"
          action="View SOS"
          onAction={() => setActivePage("sos")}
        />

        {sosAlerts.length === 0 ? (
          <EmptyState
            icon={Siren}
            title="No SOS alerts"
            text="Emergency SOS alerts will appear here."
          />
        ) : (
          <div className="activity-list">

            {sosAlerts.slice(0, 5).map((alert) => (

              <div
                className="activity-item"
                key={alert.id}
              >

                <div className="activity-icon red-icon">
                  <Siren size={17} />
                </div>

                <div className="activity-content">
                  <strong>Emergency SOS</strong>

                  <span>
                    {alert.description}
                  </span>

                  <small>
                    {formatDate(alert.created_at)}
                  </small>
                </div>

                <StatusBadge
                  value={alert.status}
                />

              </div>

            ))}

          </div>
        )}

      </section>

    </div>
  );
}


/* =========================
   SECURITY DASHBOARD
========================= */

function SecurityDashboard({ setActivePage }) {
  const [alerts, setAlerts] = useState([]);
  const [incidents, setIncidents] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [alertsData, incidentsData] = await Promise.all([
        apiRequest("/alerts"),
        apiRequest("/incidents"),
      ]);

      setAlerts(Array.isArray(alertsData) ? alertsData : []);
      setIncidents(
        Array.isArray(incidentsData) ? incidentsData : []
      );

    } catch (err) {
      console.error(err);
      setError(err.message || "Failed to load security operations data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const activeAlerts = alerts.filter(
    (item) => item.status === "active"
  );

  const highAlerts = alerts.filter(
    (item) =>
      item.severity === "high" ||
      item.severity === "critical"
  );

  const unresolvedIncidents = incidents.filter(
    (item) => item.status !== "resolved"
  );

  return (
    <div className="dashboard-page">

      <div className="page-heading-row">

        <div>
          <h1>Security Operations Center</h1>
          <p>
            Monitor campus safety events and respond to active threats.
          </p>
        </div>

        <button
          className="refresh-button"
          onClick={loadData}
        >
          <RefreshCw size={17} />
          Refresh
        </button>

      </div>

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}


      <div className="stats-grid">

        <StatCard
          title="Active Alerts"
          value={activeAlerts.length}
          icon={Bell}
          tone="red"
        />

        <StatCard
          title="High Severity"
          value={highAlerts.length}
          icon={ShieldAlert}
          tone="orange"
        />

        <StatCard
          title="Open Incidents"
          value={unresolvedIncidents.length}
          icon={FileText}
          tone="blue"
        />

        <StatCard
          title="System Status"
          value="Online"
          icon={Activity}
          tone="green"
        />

      </div>


      <div className="two-column-grid">

        <section className="panel">

          <PanelHeader
            icon={Bell}
            title="Latest Alerts"
            action="View All"
            onAction={() => setActivePage("alerts")}
          />

          {loading ? (
            <LoadingState />
          ) : alerts.length === 0 ? (
            <EmptyState
              icon={Bell}
              title="No alerts"
              text="There are currently no generated alerts."
            />
          ) : (
            <div className="activity-list">

              {alerts.slice(0, 6).map((alert) => (

                <div
                  className="activity-item"
                  key={alert.id}
                >

                  <div className="activity-icon red-icon">
                    <AlertTriangle size={17} />
                  </div>

                  <div className="activity-content">

                    <strong>
                      {alert.alert_type}
                    </strong>

                    <span>
                      {alert.location}
                    </span>

                    <small>
                      {formatDate(alert.created_at)}
                    </small>

                  </div>

                  <StatusBadge
                    value={alert.severity}
                  />

                </div>

              ))}

            </div>
          )}

        </section>


        <section className="panel">

          <PanelHeader
            icon={FileText}
            title="Recent Incidents"
            action="Manage"
            onAction={() => setActivePage("incidents")}
          />

          {incidents.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No incidents"
              text="Reported incidents will appear here."
            />
          ) : (
            <div className="activity-list">

              {incidents.slice(0, 6).map((incident) => (

                <div
                  className="activity-item"
                  key={incident.id}
                >

                  <div className="activity-icon blue-icon">
                    <FileText size={17} />
                  </div>

                  <div className="activity-content">

                    <strong>
                      {incident.incident_type}
                    </strong>

                    <span>
                      {incident.location}
                    </span>

                    <small>
                      NLP: {incident.nlp_category || "Pending"}
                    </small>

                  </div>

                  <StatusBadge
                    value={incident.status}
                  />

                </div>

              ))}

            </div>
          )}

        </section>

      </div>


      <section className="quick-actions-panel">

        <div>
          <h3>Security Operations</h3>
          <p>
            Access monitoring and response tools.
          </p>
        </div>

        <div className="quick-actions">

          <button
            onClick={() => setActivePage("cctv")}
          >
            <Camera size={18} />
            CCTV Intelligence
          </button>

          <button
            onClick={() => setActivePage("alerts")}
          >
            <Bell size={18} />
            Manage Alerts
          </button>

          <button
            onClick={() => setActivePage("analytics")}
          >
            <BarChart3 size={18} />
            Analytics
          </button>

        </div>

      </section>

    </div>
  );
}


/* =========================
   ADMIN DASHBOARD
========================= */

function AdminDashboard({ setActivePage }) {
  const [alerts, setAlerts] = useState([]);
  const [incidents, setIncidents] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [alertsData, incidentsData] = await Promise.all([
        apiRequest("/alerts"),
        apiRequest("/incidents"),
      ]);

      setAlerts(Array.isArray(alertsData) ? alertsData : []);
      setIncidents(Array.isArray(incidentsData) ? incidentsData : []);

    } catch (err) {
      console.error(err);
      setError(err.message || "Failed to load administration dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const activeAlerts = alerts.filter(
    (alert) => alert.status === "active"
  );

  const criticalAlerts = alerts.filter(
    (alert) =>
      alert.severity === "high" ||
      alert.severity === "critical"
  );

  const resolvedIncidents = incidents.filter(
    (incident) => incident.status === "resolved"
  );

  return (
    <div className="dashboard-page">

      <div className="page-heading-row">

        <div>
          <h1>Administration Dashboard</h1>
          <p>
            Campus-wide safety intelligence and system overview.
          </p>
        </div>

        <button
          className="refresh-button"
          onClick={loadData}
        >
          <RefreshCw size={17} />
          Refresh
        </button>

      </div>

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}


      {loading ? (
        <LoadingState />
      ) : (
        <>
          <div className="stats-grid">

        <StatCard
          title="Total Alerts"
          value={alerts.length}
          icon={Bell}
          tone="blue"
        />

        <StatCard
          title="Active Alerts"
          value={activeAlerts.length}
          icon={ShieldAlert}
          tone="red"
        />

        <StatCard
          title="Critical Alerts"
          value={criticalAlerts.length}
          icon={AlertTriangle}
          tone="orange"
        />

        <StatCard
          title="Resolved Incidents"
          value={resolvedIncidents.length}
          icon={CheckCircle}
          tone="green"
        />

      </div>


      <div className="admin-overview-grid">

        <section className="panel">

          <PanelHeader
            icon={Shield}
            title="Platform Status"
          />

          <div className="system-status-list">

            <SystemStatus
              label="Backend API"
              status="Operational"
            />

            <SystemStatus
              label="Database"
              status="Operational"
            />

            <SystemStatus
              label="AI Detection"
              status="Operational"
            />

            <SystemStatus
              label="Alert Management"
              status="Operational"
            />

            <SystemStatus
              label="Authentication"
              status="Operational"
            />

          </div>

        </section>


        <section className="panel">

          <PanelHeader
            icon={Activity}
            title="System Activity"
          />

          <div className="admin-activity">

            <div>
              <strong>{alerts.length}</strong>
              <span>Total alerts generated</span>
            </div>

            <div>
              <strong>{incidents.length}</strong>
              <span>Total incidents reported</span>
            </div>

            <div>
              <strong>
                {incidents.filter(
                  (item) => item.nlp_category
                ).length}
              </strong>
              <span>Incidents NLP analyzed</span>
            </div>

          </div>

        </section>

      </div>


      <section className="quick-actions-panel">

        <div>
          <h3>Administration Tools</h3>
          <p>
            Manage and inspect the CampusGuard AI platform.
          </p>
        </div>

        <div className="quick-actions">

          <button
            onClick={() => setActivePage("alerts")}
          >
            <Bell size={18} />
            Alerts
          </button>

          <button
            onClick={() => setActivePage("incidents")}
          >
            <FileText size={18} />
            Incidents
          </button>

          <button
            onClick={() => setActivePage("analytics")}
          >
            <BarChart3 size={18} />
            Analytics
          </button>

          <button
            onClick={() => setActivePage("settings")}
          >
            <Settings size={18} />
            Settings
          </button>

        </div>

      </section>
        </>
      )}

    </div>
  );
}


/* =========================
   INCIDENT DETAILS MODAL
========================= */

function IncidentDetailsModal({
  incident,
  onClose,
  onUpdateStatus,
  isStudent,
}) {
  const [logs, setLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [blobUrl, setBlobUrl] = useState(null);
  const [blobType, setBlobType] = useState("");
  const [loadingAttachment, setLoadingAttachment] = useState(false);
  const [attachmentError, setAttachmentError] = useState("");

  useEffect(() => {
    if (incident?.id) {
      setLoadingLogs(true);
      apiRequest(`/incidents/${incident.id}/logs`)
        .then((data) => setLogs(Array.isArray(data) ? data : []))
        .catch(() => setLogs([]))
        .finally(() => setLoadingLogs(false));
    }
  }, [incident?.id]);

  useEffect(() => {
    let activeUrl = null;
    let isCancelled = false;

    if (incident?.attachment) {
      setLoadingAttachment(true);
      setAttachmentError("");
      setBlobUrl(null);
      setBlobType("");

      fetchAttachmentBlob(incident.attachment)
        .then((blob) => {
          if (isCancelled) return;
          const url = URL.createObjectURL(blob);
          activeUrl = url;
          setBlobUrl(url);
          setBlobType(blob.type || "");
        })
        .catch((err) => {
          if (isCancelled) return;
          setAttachmentError(err.message || "Failed to load attachment.");
        })
        .finally(() => {
          if (!isCancelled) setLoadingAttachment(false);
        });
    }

    return () => {
      isCancelled = true;
      if (activeUrl) {
        URL.revokeObjectURL(activeUrl);
      }
    };
  }, [incident?.attachment]);

  if (!incident) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h3>
            <FileText size={18} color="#2563eb" />
            Incident #{incident.id}: {incident.incident_type}
          </h3>
          <button
            className="modal-close-button"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="modal-meta-grid">
            <div className="modal-meta-item">
              <span>Status</span>
              <div>
                <StatusBadge value={incident.status} />
              </div>
            </div>

            <div className="modal-meta-item">
              <span>Urgency</span>
              <div>
                <StatusBadge value={incident.nlp_urgency || "Normal"} />
              </div>
            </div>

            <div className="modal-meta-item">
              <span>Location</span>
              <strong>{incident.location || "Campus"}</strong>
            </div>

            <div className="modal-meta-item">
              <span>Reported At</span>
              <strong>{formatDate(incident.created_at)}</strong>
            </div>

            {!isStudent && (
              <div className="modal-meta-item">
                <span>Reporter</span>
                <strong>User #{incident.user_id}</strong>
              </div>
            )}
          </div>

          <div className="modal-section">
            <div className="modal-section-title">
              Full Incident Description
            </div>
            <div className="modal-description-box">
              {incident.description || "No description provided."}
            </div>
          </div>

          <div className="modal-section">
            <div className="modal-section-title">
              NLP Automated Analysis
            </div>
            <div className="modal-nlp-box">
              <div>
                <strong>Classification: {incident.nlp_category || "General Safety"}</strong>
                <div style={{ marginTop: "4px", fontSize: "11px", color: "#1e40af" }}>
                  Urgency: {incident.nlp_urgency || "Normal"}
                </div>
              </div>
              <StatusBadge value={incident.nlp_urgency || "Normal"} />
            </div>
          </div>

          {incident.attachment && (
            <div className="modal-section">
              <div className="modal-section-title">Attached Evidence / Photo</div>
              {loadingAttachment ? (
                <div style={{ fontSize: "12px", color: "#64748b", padding: "8px 0" }}>Loading attachment preview...</div>
              ) : attachmentError ? (
                <div className="error-message" style={{ margin: "8px 0", fontSize: "12px" }}>
                  {attachmentError}
                </div>
              ) : blobUrl ? (
                <div className="incident-attachment-preview">
                  {blobType === "application/pdf" || incident.attachment.toLowerCase().endsWith(".pdf") ? (
                    <div style={{ padding: "16px", textAlign: "center", background: "#f8fafc", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
                      <FileText size={36} color="#dc2626" style={{ margin: "0 auto 8px" }} />
                      <div style={{ fontSize: "13px", fontWeight: 600, color: "#1e293b" }}>PDF Document Attached</div>
                      <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>Secured incident evidence document</div>
                    </div>
                  ) : (
                    <a href={blobUrl} target="_blank" rel="noopener noreferrer">
                      <img src={blobUrl} alt="Attachment" onError={(e) => { e.target.style.display = 'none'; }} />
                    </a>
                  )}
                  <div style={{ padding: "6px 10px", fontSize: "11px", background: "#f8fafc" }}>
                    <a href={blobUrl} target="_blank" rel="noopener noreferrer" style={{ color: "#2563eb", fontWeight: 600 }}>
                      View Full Attachment ↗
                    </a>
                  </div>
                </div>
              ) : null}
            </div>
          )}

          <div className="modal-section">
            <div className="modal-section-title">Incident Audit Timeline</div>
            {loadingLogs ? (
              <div style={{ fontSize: "12px", color: "#64748b", padding: "8px 0" }}>Loading audit trail...</div>
            ) : logs.length === 0 ? (
              <div style={{ fontSize: "12px", color: "#64748b", padding: "8px 0" }}>No audit log events recorded yet.</div>
            ) : (
              <div className="incident-timeline">
                {logs.map((log) => (
                  <div key={log.id} className={`timeline-event ${log.action}`}>
                    <div className="timeline-event-header">
                      <span className="timeline-event-title">{log.action.replace('_', ' ')}</span>
                      <span className="timeline-event-time">{formatDate(log.created_at)}</span>
                    </div>
                    <div className="timeline-event-details">{log.details}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="modal-footer">
          <div className="table-actions">
            {!isStudent && incident.status === "submitted" && (
              <button
                className="small-button"
                onClick={async () => {
                  await onUpdateStatus(incident.id, "acknowledged");
                  onClose();
                }}
              >
                Acknowledge
              </button>
            )}

            {!isStudent && incident.status === "acknowledged" && (
              <button
                className="small-button success-button"
                onClick={async () => {
                  await onUpdateStatus(incident.id, "resolved");
                  onClose();
                }}
              >
                Resolve
              </button>
            )}
          </div>

          <button
            className="small-button"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}


function StudentReportModal({ onClose, onSuccess }) {
  const [incidentType, setIncidentType] = useState("Suspicious Activity");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [attachmentFile, setAttachmentFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    if (!location.trim() || !description.trim()) {
      setError("Please provide both the incident location and a description.");
      return;
    }

    try {
      setSubmitting(true);
      setError("");

      let attachmentUrl = null;
      if (attachmentFile) {
        const formData = new FormData();
        formData.append("file", attachmentFile);
        const uploadRes = await apiRequest("/incidents/upload", {
          method: "POST",
          body: formData,
        });
        attachmentUrl = uploadRes.attachment_url;
      }

      const data = await apiRequest("/incidents", {
        method: "POST",
        body: JSON.stringify({
          incident_type: incidentType,
          location: location.trim(),
          description: description.trim(),
          attachment: attachmentUrl,
        }),
      });

      onSuccess(data.incident_id || data.id);
    } catch (err) {
      setError(err.message || "Failed to submit incident report.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>
            <FileText size={18} color="#2563eb" />
            Report New Incident
          </h3>
          <button className="modal-close-button" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && (
              <div className="error-message page-alert">
                <AlertTriangle size={18} />
                {error}
              </div>
            )}

            <div className="form-group">
              <label>Incident Type</label>
              <select
                value={incidentType}
                onChange={(e) => setIncidentType(e.target.value)}
              >
                <option value="Suspicious Activity">Suspicious Activity</option>
                <option value="Medical Emergency">Medical Emergency</option>
                <option value="Fighting">Fighting</option>
                <option value="Weapon">Weapon</option>
                <option value="Fall">Fall</option>
                <option value="Restricted Area">Restricted Area</option>
                <option value="Fire">Fire</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div className="form-group">
              <label>Incident Location</label>
              <input
                type="text"
                placeholder="e.g., Main Library 2nd Floor, Room 204"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label>Description of Safety Concern</label>
              <textarea
                placeholder="Describe what occurred, any hazards, or persons involved..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows="4"
              />
            </div>

            <div className="form-group">
              <label>Optional Photo / Evidence Attachment</label>
              <input
                type="file"
                accept="image/*,.pdf"
                onChange={(e) => setAttachmentFile(e.target.files[0] || null)}
              />
            </div>
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="small-button"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="primary-button"
              disabled={submitting || !location.trim() || !description.trim()}
            >
              {submitting ? "Submitting..." : "Submit Incident Report"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


/* =========================
   INCIDENTS
========================= */

function IncidentsPage({ user }) {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [showReportModal, setShowReportModal] = useState(false);
  const [reportSuccess, setReportSuccess] = useState("");

  async function loadIncidents() {
    try {
      setLoading(true);
      setError("");

      const data = await apiRequest("/incidents");

      setIncidents(Array.isArray(data) ? data : []);

    } catch (err) {
      setError(err.message || "Unable to load incidents.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadIncidents();
  }, []);

  async function updateStatus(id, status) {
    try {
      await apiRequest(
        `/incidents/${id}/status?status=${encodeURIComponent(status)}`,
        {
          method: "PATCH",
        }
      );

      await loadIncidents();

    } catch (err) {
      setError(err.message || "Unable to update incident.");
    }
  }

  const isStudent = user.role === "student";

  return (
    <div className="content-page">

      <PageHeading
        title={isStudent ? "My Incidents" : "Incident Management"}
        description={
          isStudent
            ? "View and report campus safety incidents."
            : "Review, analyze and manage reported campus incidents."
        }
        action={isStudent ? "+ Report Incident" : null}
        onAction={
          isStudent
            ? () => {
                setShowReportModal(true);
                setReportSuccess("");
              }
            : null
        }
        onRefresh={loadIncidents}
      />

      {reportSuccess && (
        <div className="success-message page-alert">
          <CheckCircle size={18} />
          {reportSuccess}
        </div>
      )}

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}

      <section className="panel table-panel">

        {loading ? (
          <LoadingState />
        ) : incidents.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No incidents found"
            text={
              isStudent
                ? "You have not submitted any incidents yet."
                : "No campus incidents have been reported."
            }
          />
        ) : (
          <div className="table-wrapper">

            <table>

              <thead>
                <tr>
                  <th>ID</th>

                  {!isStudent && <th>User</th>}

                  <th>Type</th>
                  <th>Location</th>
                  <th>NLP Category</th>
                  <th>Urgency</th>
                  <th>Status</th>
                  <th>Created</th>

                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>

                {incidents.map((incident) => (

                  <Fragment key={incident.id}>
                    <tr>

                      <td>#{incident.id}</td>

                      {!isStudent && (
                        <td>
                          User #{incident.user_id}
                        </td>
                      )}

                      <td>
                        <strong>
                          {incident.incident_type}
                        </strong>
                      </td>

                      <td>{incident.location}</td>

                      <td>
                        {incident.nlp_category || "-"}
                      </td>

                      <td>
                        <StatusBadge
                          value={incident.nlp_urgency || "-"}
                        />
                      </td>

                      <td>
                        <StatusBadge
                          value={incident.status}
                        />
                      </td>

                      <td>
                        {formatDate(incident.created_at)}
                      </td>

                      <td>

                        <div className="table-actions">

                          <button
                            className="small-button info-button"
                            onClick={() => setSelectedIncident(incident)}
                            title="View full report description and NLP analysis"
                          >
                            <Eye size={12} style={{ marginRight: "3px" }} />
                            Details
                          </button>

                          <button
                            className="small-button"
                            onClick={() =>
                              setExpandedId(
                                expandedId === incident.id ? null : incident.id
                              )
                            }
                            title={
                              expandedId === incident.id
                                ? "Hide inline description"
                                : "Expand inline description"
                            }
                          >
                            {expandedId === incident.id ? "Hide" : "Expand"}
                          </button>

                          {!isStudent && (
                            <>
                              {incident.status === "submitted" && (
                                <button
                                  className="small-button"
                                  onClick={() =>
                                    updateStatus(
                                      incident.id,
                                      "acknowledged"
                                    )
                                  }
                                >
                                  Acknowledge
                                </button>
                              )}

                              {incident.status === "acknowledged" && (
                                <button
                                  className="small-button success-button"
                                  onClick={() =>
                                    updateStatus(
                                      incident.id,
                                      "resolved"
                                    )
                                  }
                                >
                                  Resolve
                                </button>
                              )}
                            </>
                          )}

                        </div>

                      </td>

                    </tr>

                    {expandedId === incident.id && (
                      <tr className="incident-expand-row">
                        <td colSpan={isStudent ? 8 : 9}>
                          <div className="incident-expand-box">
                            <div>
                              <strong>Incident Description:</strong>
                              <p>{incident.description || "No description provided."}</p>
                            </div>
                            <div style={{ display: "flex", gap: "18px", flexWrap: "wrap", fontSize: "11px", color: "#64748b" }}>
                              <span><strong>NLP Category:</strong> {incident.nlp_category || "Uncategorized"}</span>
                              <span><strong>NLP Urgency:</strong> {incident.nlp_urgency || "Normal"}</span>
                              <span><strong>Submitted:</strong> {formatDate(incident.created_at)}</span>
                              {!isStudent && <span><strong>Reporter:</strong> User #{incident.user_id}</span>}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>

                ))}

              </tbody>

            </table>

          </div>
        )}

      </section>

      {selectedIncident && (
        <IncidentDetailsModal
          incident={selectedIncident}
          onClose={() => setSelectedIncident(null)}
          onUpdateStatus={updateStatus}
          isStudent={isStudent}
        />
      )}

      {showReportModal && (
        <StudentReportModal
          onClose={() => setShowReportModal(false)}
          onSuccess={(newId) => {
            setShowReportModal(false);
            setReportSuccess(`Incident reported successfully. ID: #${newId}`);
            loadIncidents();
          }}
        />
      )}

    </div>
  );
}


/* =========================
   ALERTS
========================= */

function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadAlerts() {
    try {
      setLoading(true);
      setError("");

      const data = await apiRequest("/alerts");

      setAlerts(Array.isArray(data) ? data : []);

    } catch (err) {
      setError(err.message || "Unable to load alerts.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAlerts();
  }, []);

  async function updateAlert(id, action) {
    try {
      await apiRequest(`/alerts/${id}/${action}`, {
        method: "PATCH",
      });

      await loadAlerts();

    } catch (err) {
      setError(err.message || "Unable to update alert.");
    }
  }

  return (
    <div className="content-page">

      <PageHeading
        title="Security Alerts"
        description="Monitor and manage generated safety alerts."
        onRefresh={loadAlerts}
      />

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}

      <section className="panel table-panel">

        {loading ? (
          <LoadingState />
        ) : alerts.length === 0 ? (
          <EmptyState
            icon={Bell}
            title="No alerts"
            text="No safety alerts are currently available."
          />
        ) : (
          <div className="table-wrapper">

            <table>

              <thead>

                <tr>
                  <th>ID</th>
                  <th>Alert</th>
                  <th>Location</th>
                  <th>Description</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>

              </thead>

              <tbody>

                {alerts.map((alert) => (

                  <tr key={alert.id}>

                    <td>#{alert.id}</td>

                    <td>
                      <strong>{alert.alert_type}</strong>
                    </td>

                    <td>{alert.location}</td>

                    <td className="description-cell">
                      {alert.description || "-"}
                    </td>

                    <td>
                      <div className="alert-severity-cell">
                        <StatusBadge
                          value={alert.severity}
                        />
                        {alert.operational_score !== null && alert.operational_score !== undefined && (
                          <span
                            className="operational-score-pill"
                            title={`Operational Severity Score: ${alert.operational_score}/100`}
                          >
                            {alert.operational_score}/100
                          </span>
                        )}
                      </div>
                    </td>

                    <td>
                      <StatusBadge
                        value={alert.escalated ? "escalated" : alert.status}
                      />
                      {alert.assigned_to && (
                        <div style={{ fontSize: "10px", color: "#64748b", marginTop: "3px" }}>
                          Officer #{alert.assigned_to}
                        </div>
                      )}
                    </td>

                    <td>
                      {formatDate(alert.created_at)}
                    </td>

                    <td>

                      <div className="table-actions">

                        {alert.status === "active" && (
                          <>
                            <button
                              className="small-button"
                              onClick={() => updateAlert(alert.id, "acknowledge")}
                            >
                              Acknowledge
                            </button>
                            <button
                              className="small-button"
                              style={{ background: "#dc2626", color: "#ffffff" }}
                              onClick={() => updateAlert(alert.id, "escalate")}
                            >
                              Escalate
                            </button>
                          </>
                        )}

                        {alert.status === "acknowledged" && (
                          <>
                            <button
                              className="small-button success-button"
                              onClick={() => updateAlert(alert.id, "resolve")}
                            >
                              Resolve
                            </button>
                            <button
                              className="small-button"
                              style={{ background: "#ea580c", color: "#ffffff" }}
                              onClick={() => updateAlert(alert.id, "escalate")}
                            >
                              Escalate
                            </button>
                          </>
                        )}

                        {alert.status === "escalated" && (
                          <button
                            className="small-button success-button"
                            onClick={() => updateAlert(alert.id, "resolve")}
                          >
                            Resolve Critical
                          </button>
                        )}

                      </div>

                    </td>

                  </tr>

                ))}

              </tbody>

            </table>

          </div>
        )}

      </section>

    </div>
  );
}

/* =========================
   CCTV
========================= */

function CCTVPage() {
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("image");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyzeFile() {
    if (!file) {
      setError("Please select a file first.");
      return;
    }

    try {
      setLoading(true);
      setError("");
      setResult(null);

      const formData = new FormData();
      formData.append("file", file);

      const token = localStorage.getItem("campusguard_token");

      const endpoint =
        mode === "video"
          ? "/camera/analyze-video"
          : "/camera/analyze";

      const response = await fetch(
        `${API_URL}${endpoint}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        }
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          handleUnauthorizedSession();
        }

        throw new Error(
          data.detail ||
          data.message ||
          "CCTV analysis failed."
        );
      }

      setResult(data);

    } catch (err) {
      console.error("CCTV ERROR:", err);
      setError(
        err.message ||
        "CCTV analysis failed."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="content-page">

      <PageHeading
        title="CCTV Intelligence"
        description="Analyze recorded CCTV images and videos using CampusGuard AI models."
      />

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}

      <div className="cctv-mode-tabs">

        <button
          className={
            mode === "image"
              ? "active"
              : ""
          }
          onClick={() => {
            setMode("image");
            setFile(null);
            setResult(null);
            setError("");
          }}
        >
          <Camera size={18} />
          Image Analysis
        </button>

        <button
          className={
            mode === "video"
              ? "active"
              : ""
          }
          onClick={() => {
            setMode("video");
            setFile(null);
            setResult(null);
            setError("");
          }}
        >
          <Video size={18} />
          Video Analysis
        </button>

      </div>

      <div className="cctv-grid">

        <section className="panel upload-panel">

          <div className="upload-icon">
            {mode === "video" ? (
              <Video size={32} />
            ) : (
              <Camera size={32} />
            )}
          </div>

          <h3>
            Upload CCTV{" "}
            {mode === "video"
              ? "Video"
              : "Image"}
          </h3>

          <p>
            {mode === "video"
              ? "Upload an MP4, AVI, MOV or MKV CCTV recording."
              : "Upload a CCTV frame for AI threat analysis."}
          </p>

          <label className={`file-drop ${loading ? "disabled" : ""}`}>

            <Upload size={24} />

            <strong>
              {file
                ? file.name
                : "Choose a file"}
            </strong>

            <span>
              Click to browse from your computer
            </span>

            <input
              type="file"
              disabled={loading}
              accept={
                mode === "video"
                  ? "video/*"
                  : "image/*"
              }
              onChange={(event) => {
                setFile(
                  event.target.files?.[0] ||
                  null
                );
                setResult(null);
                setError("");
              }}
              style={{
                display: "none",
              }}
            />

          </label>

          <button
            className="primary-button"
            onClick={analyzeFile}
            disabled={!file || loading}
          >
            {loading
              ? "Analyzing..."
              : "Analyze CCTV"}
          </button>

        </section>

        <section className="panel">

          <div className="panel-header">

            <div>
              <h3>
                AI Analysis Results
              </h3>

              <p>
                Detection and risk information from the backend.
              </p>
            </div>

          </div>

          {!result ? (
            <EmptyState
              icon={Camera}
              title="Awaiting analysis"
              text="Upload CCTV media and click Analyze CCTV to view AI detection results."
            />
          ) : (
            <CCTVResult
              result={result}
              mode={mode}
              onRetry={analyzeFile}
            />
          )}

        </section>

      </div>

    </div>
  );
}


/* =========================
   CCTV RESULT
========================= */

function CCTVResult({ result, mode, onRetry }) {
  const isVideo =
    mode === "video" ||
    result?.frames_analyzed !== undefined ||
    result?.detector_analysis !== undefined;

  const hasRisk = Boolean(result?.risk && typeof result.risk === "object");
  const riskLevel = hasRisk ? (result.risk.risk_level || "Unknown") : "Not Calculated";
  const riskScore = hasRisk ? (result.risk.risk_score ?? null) : null;
  const riskScoreType = result?.risk?.risk_score_type;
  const modelType = result?.risk?.model_type;
  const confidence = result?.risk?.confidence;
  const factors = Array.isArray(result?.risk?.factors) ? result.risk.factors : [];

  const analysisStatus = result?.analysis_status || (isVideo ? "success" : null);
  const processingErrors = result?.processing_errors || {};
  const failedDetectors = Object.keys(processingErrors);
  const hasProcessingErrors = failedDetectors.length > 0;
  const detectorStatuses = result?.detector_statuses || {};
  const detectorAnalysis = result?.detector_analysis || {};

  const personCount = result?.person_count ?? 0;
  const fallDetected = result?.fall_detected;
  const fightDetected = result?.fight_detected;
  const fightProximityDetected = Boolean(result?.fight_proximity_detected);
  const weaponDetected = result?.weapon_detected;
  const restrictedDetected = result?.restricted_entry;
  const afterHoursDetected = Boolean(result?.after_hours);
  const loiteringDetected = Boolean(result?.loitering_detected);

  // Derive operational severity robustly from risk object, root payload, or detection signals
  const derivedOperationalSeverity = weaponDetected
    ? "Critical"
    : (fallDetected || restrictedDetected || (riskLevel === "High")
      ? "High"
      : (loiteringDetected || afterHoursDetected
        ? "Medium"
        : (hasRisk ? "Low" : null)));

  const operationalSeverity =
    result?.risk?.operational_severity ||
    result?.operational_severity ||
    derivedOperationalSeverity;

  const operationalScore =
    result?.risk?.operational_score ??
    result?.operational_score ??
    (operationalSeverity?.toLowerCase() === "critical"
      ? 100
      : (operationalSeverity?.toLowerCase() === "high"
        ? 80
        : (operationalSeverity?.toLowerCase() === "medium"
          ? 50
          : (operationalSeverity?.toLowerCase() === "low" ? 20 : null))));

  // Helper for detector card state in video mode
  const getVideoSignalStatus = (detectorKey, detectedVal, frameCount, extraText) => {
    const analysisVal = detectorAnalysis[detectorKey];
    const hasError = analysisVal === "error" || Boolean(processingErrors[detectorKey]) || detectedVal === null;
    if (hasError) {
      return {
        badge: "Unverified / Error",
        detail: processingErrors[detectorKey]
          ? `Error: ${processingErrors[detectorKey]}`
          : "Processing error — signal unverified",
        cssClass: "status-unverified",
      };
    }
    if (analysisVal === "detected" || detectedVal === true) {
      return {
        badge: "Threat Detected",
        detail: `${frameCount ? `${frameCount} frame${frameCount === 1 ? "" : "s"} flagged` : "Detected"}${extraText ? ` • ${extraText}` : ""}`,
        cssClass: "status-threat",
      };
    }
    return {
      badge: "Clear",
      detail: extraText || "0 flagged frames (verified clear)",
      cssClass: "status-clear",
    };
  };

  return (
    <div className="cctv-result">
      {/* 1. Overall Analysis Status Banner */}
      {analysisStatus === "success" && (
        <div className="cctv-status-banner status-success-banner">
          <CheckCircle size={17} />
          <div>
            <strong>Analysis Complete</strong>
            <span>
              All 5 vision detectors operational across {result?.frames_analyzed ?? 1} sampled frames
              {result?.video_duration_seconds ? ` (${result.video_duration_seconds}s recording duration)` : ""}.
            </span>
          </div>
        </div>
      )}

      {analysisStatus === "partial" && (
        <div className="cctv-status-banner status-warning-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>Partial Analysis Warning</strong>
            <p>
              Some vision detectors encountered errors ({failedDetectors.join(", ")}).
              Unanalyzed detector fields cannot be verified clear and are reported as unverified.
            </p>
          </div>
        </div>
      )}

      {analysisStatus === "failed" && (
        <div className="cctv-status-banner status-error-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>Analysis Incomplete</strong>
            <p>Vision detectors encountered fatal processing errors. Please retry with a valid video file.</p>
            {onRetry && (
              <button className="cctv-retry-button" onClick={onRetry}>
                <RefreshCw size={14} /> Retry Analysis
              </button>
            )}
          </div>
        </div>
      )}

      {/* 2. Dual Risk & Operational Severity Assessment */}
      <div className="cctv-dual-scores">
        {/* Card A: Operational Severity Score */}
        <div className="risk-result-card score-card-operational">
          <div>
            <span>Operational Threat Severity</span>
            {operationalSeverity ? (
              <strong className={getRiskTextClass(operationalSeverity)}>
                {operationalSeverity.toUpperCase()}
              </strong>
            ) : (
              <strong style={{ color: "#64748b" }}>
                {hasRisk ? "LOW" : "NOT CALCULATED"}
              </strong>
            )}
            <div className="risk-model-caption">
              <span className="risk-model-tag">
                Operational Triage Scale: Low=20, Med=50, High=80, Crit=100
              </span>
            </div>
          </div>

          <div className="risk-score">
            <span>Operational Severity Score</span>
            {operationalScore !== null ? (
              <>
                <div>
                  <strong>{operationalScore}</strong>
                  <small>/ 100</small>
                </div>
                <div className="risk-score-tier-label">
                  Actionable response priority (not a probability)
                </div>
              </>
            ) : (
              <>
                <strong style={{ fontSize: "20px", color: "#64748b" }}>N/A</strong>
                <small>Not Calculated</small>
              </>
            )}
          </div>
        </div>

        {/* Card B: ML Risk Prediction */}
        <div className="risk-result-card score-card-ml">
          <div>
            <span>ML Multi-Signal Prediction</span>
            {hasRisk ? (
              <strong className={getRiskTextClass(riskLevel)}>
                {riskLevel.toUpperCase()}
              </strong>
            ) : (
              <strong style={{ color: "#64748b" }}>
                NOT CALCULATED
              </strong>
            )}
            {modelType && (
              <div className="risk-model-caption" title={modelType}>
                <span className="risk-model-tag">
                  {modelType.includes("Random Forest") ? "ML Classifier: Trained Model (Low/Med/High)" : "Rule-Based Risk Model"}
                </span>
                {confidence !== null && confidence !== undefined && (
                  <span className="risk-confidence-tag">
                    Tree Agreement: {Math.round(confidence * 100)}%
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="risk-score">
            <span>ML Risk Score</span>
            {hasRisk && riskScore !== null ? (
              <>
                <div>
                  <strong>{riskScore}</strong>
                  <small>/ 100</small>
                </div>
                <div className="risk-score-tier-label">
                  {riskScoreType === "discrete_tier_score"
                    ? "Multi-signal learned score (not a probability)"
                    : "Rule-based score (not a probability)"}
                </div>
              </>
            ) : (
              <>
                <strong style={{ fontSize: "20px", color: "#64748b" }}>N/A</strong>
                <small>Not Calculated</small>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 3. Stats Grid */}
      {isVideo ? (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-content">
              <span>Frames Analyzed</span>
              <strong>{result?.frames_analyzed ?? 0}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-content">
              <span>Video Duration</span>
              <strong>
                {result?.video_duration_seconds !== null && result?.video_duration_seconds !== undefined
                  ? `${result.video_duration_seconds}s`
                  : "N/A"}
              </strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-content">
              <span>People Detected</span>
              <strong>{personCount}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-content">
              <span>Loitering Dwell Window</span>
              <strong>
                {result?.loitering_threshold_seconds
                  ? `${result.loitering_threshold_seconds}s`
                  : "5s"}
              </strong>
            </div>
          </div>
        </div>
      ) : (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-content">
              <span>People Detected</span>
              <strong>{personCount}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-content">
              <span>Risk Level</span>
              <strong className={getRiskTextClass(riskLevel)}>{riskLevel}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-content">
              <span>Operational Score</span>
              <strong>{hasRisk && operationalScore !== null ? `${operationalScore} / 100` : "N/A"}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-content">
              <span>ML Risk Score</span>
              <strong>{hasRisk && riskScore !== null ? `${riskScore} / 100` : "N/A"}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-content">
              <span>Model Confidence</span>
              <strong>
                {hasRisk && typeof confidence === "number"
                  ? `${Math.round(confidence * 100)}%`
                  : (result?.confidence !== undefined ? `${Math.round(result.confidence * 100)}%` : "N/A")}
              </strong>
            </div>
          </div>
        </div>
      )}

      {/* 4. Vision Detection Signals Grid */}
      <div className="panel-section">
        <h4>{isVideo ? "Temporal & Spatial Vision Signals" : "Frame Vision Detections"}</h4>

        {isVideo ? (
          <div className="detection-grid">
            {/* Weapon Detection Card */}
            {(() => {
              const status = getVideoSignalStatus(
                "weapon_detection",
                weaponDetected,
                result?.weapon_frames,
                result?.detected_weapons?.length
                  ? result.detected_weapons.map(w => typeof w === "string" ? w : (w.weapon || w.name || "weapon")).join(", ")
                  : null
              );
              return (
                <div className={`cctv-signal-card ${status.cssClass}`}>
                  <div className="signal-card-header">
                    <strong>Weapon Detection</strong>
                    <span className={`signal-badge ${status.cssClass}`}>{status.badge}</span>
                  </div>
                  <span className="signal-card-detail">{status.detail}</span>
                  {result?.detected_weapons?.length > 0 && (
                    <div className="weapon-tags-inline">
                      {result.detected_weapons.map((w, idx) => (
                        <span key={idx} className="weapon-tag-pill">
                          {typeof w === "string" ? w : `${w.weapon || w.name || "weapon"}${w.confidence ? ` (${Math.round(w.confidence * 100)}%)` : ""}`}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Fall Detection Card */}
            {(() => {
              const status = getVideoSignalStatus("fall_detection", fallDetected, result?.fall_frames);
              return (
                <div className={`cctv-signal-card ${status.cssClass}`}>
                  <div className="signal-card-header">
                    <strong>Fall Detection</strong>
                    <span className={`signal-badge ${status.cssClass}`}>{status.badge}</span>
                  </div>
                  <span className="signal-card-detail">{status.detail}</span>
                </div>
              );
            })()}

            {/* Restricted Zone Entry Card */}
            {(() => {
              const status = getVideoSignalStatus(
                "restricted_zone",
                restrictedDetected,
                result?.restricted_entry_frames,
                result?.restricted_zone || null
              );
              return (
                <div className={`cctv-signal-card ${status.cssClass}`}>
                  <div className="signal-card-header">
                    <strong>Restricted Zone Entry</strong>
                    <span className={`signal-badge ${status.cssClass}`}>{status.badge}</span>
                  </div>
                  <span className="signal-card-detail">{status.detail}</span>
                </div>
              );
            })()}

            {/* Loitering Detection Card */}
            {(() => {
              const status = getVideoSignalStatus(
                "loitering_detection",
                loiteringDetected,
                result?.loitering_frames,
                result?.loitering_person_ids?.length
                  ? `Tracked IDs: ${result.loitering_person_ids.join(", ")}`
                  : null
              );
              return (
                <div className={`cctv-signal-card ${status.cssClass}`}>
                  <div className="signal-card-header">
                    <strong>Loitering Pattern</strong>
                    <span className={`signal-badge ${status.cssClass}`}>{status.badge}</span>
                  </div>
                  <span className="signal-card-detail">{status.detail}</span>
                </div>
              );
            })()}

            {/* Fight Proximity Card (Experimental Heuristic) */}
            {(() => {
              const fightStatusVal = detectorAnalysis["fight_detection"];
              const hasError = fightStatusVal === "error" || Boolean(processingErrors["fight_detection"]);
              if (hasError) {
                return (
                  <div className="cctv-signal-card status-unverified">
                    <div className="signal-card-header">
                      <strong>Fight Proximity</strong>
                      <span className="signal-badge status-unverified">Unverified / Error</span>
                    </div>
                    <span className="signal-card-detail">Pose detection error during frame sampling</span>
                  </div>
                );
              }
              const isFlagged = fightStatusVal === "proximity_flagged" || fightProximityDetected;
              return (
                <div className={`cctv-signal-card ${isFlagged ? "status-experimental" : "status-clear"}`}>
                  <div className="signal-card-header">
                    <div className="signal-title-with-pill">
                      <strong>Fight Proximity</strong>
                      <span className="experimental-pill">Experimental</span>
                    </div>
                    <span className={`signal-badge ${isFlagged ? "status-experimental" : "status-clear"}`}>
                      {isFlagged ? "Proximity Flagged" : "Clear"}
                    </span>
                  </div>
                  <span className="signal-card-detail">
                    {isFlagged
                      ? `${result?.fight_proximity_frames ?? 1} frame${result?.fight_proximity_frames === 1 ? "" : "s"} flagged (pose distance < 0.25)`
                      : "0 close proximity interactions detected"}
                  </span>
                  <div className="signal-experimental-disclaimer">
                    * Experimental 2D pose proximity heuristic only. Temporal action recognition is not implemented; proximity flags do not confirm physical violence.
                  </div>
                </div>
              );
            })()}

            {/* Operating Schedule Card */}
            <div className={`cctv-signal-card ${afterHoursDetected ? "status-threat" : "status-clear"}`}>
              <div className="signal-card-header">
                <strong>Operating Schedule</strong>
                <span className={`signal-badge ${afterHoursDetected ? "status-threat" : "status-clear"}`}>
                  {afterHoursDetected ? "After-Hours Activity" : "Standard Hours"}
                </span>
              </div>
              <span className="signal-card-detail">
                {result?.after_hours_message || (afterHoursDetected ? "Movement during closed campus hours" : "Within scheduled operating hours")}
              </span>
            </div>
          </div>
        ) : (
          <div className="detection-grid">
            <div className={`detection-item ${fallDetected ? "detected" : "not-detected"}`}>
              <span>Fall Detection</span>
              <strong>{fallDetected ? "Detected" : "Not Detected"}</strong>
            </div>
            <div className={`detection-item ${fightDetected ? "detected" : "not-detected"}`}>
              <span>Fight Detection</span>
              <strong>{fightDetected ? "Detected" : "Not Detected"}</strong>
            </div>
            <div className={`detection-item ${weaponDetected ? "detected" : "not-detected"}`}>
              <span>Weapon Detection</span>
              <strong>{weaponDetected ? "Detected" : "Not Detected"}</strong>
            </div>
            <div className={`detection-item ${restrictedDetected ? "detected" : "not-detected"}`}>
              <span>Restricted Entry</span>
              <strong>{restrictedDetected ? "Detected" : "Not Detected"}</strong>
            </div>
            <div className={`detection-item ${afterHoursDetected ? "detected" : "not-detected"}`}>
              <span>After-Hours Activity</span>
              <strong>{afterHoursDetected ? "Detected" : "Not Detected"}</strong>
            </div>
            <div className="detection-item not-detected" style={{ opacity: 0.85 }}>
              <span>Loitering</span>
              <strong style={{ color: "#64748b" }}>Requires Video</strong>
            </div>
          </div>
        )}
      </div>

      {/* 5. Contributing Risk Factors */}
      {factors.length > 0 && (
        <div className="panel-section factors-section">
          <h4>Contributing Risk Factors</h4>
          <div className="factors-list">
            {factors.map((f, idx) => {
              const sev = (f.severity || "low").toLowerCase();
              return (
                <div key={idx} className="factor-item">
                  <div className="factor-info">
                    <span className="factor-name">{f.factor}</span>
                  </div>
                  <div className="factor-meta">
                    <span className={`factor-severity-badge sev-${sev}`}>
                      {f.severity || "Normal"}
                    </span>
                    <span className="factor-impact">{f.impact}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 6. Alert Creation Outcome */}
      {result?.alert_id ? (
        <div className="success-message page-alert alert-created-banner">
          <CheckCircle size={20} />
          <div>
            <strong>Persistent Alert Created: Alert #{result.alert_id}</strong>
            <p>High-priority threat logged to operational database ledger for dispatcher resolution.</p>
          </div>
        </div>
      ) : (
        <div className="info-message page-alert no-alert-banner">
          <Shield size={20} />
          <div>
            <strong>No Alert Created</strong>
            <p>Safety parameters are within baseline tolerances. No operational alert record was generated.</p>
          </div>
        </div>
      )}

      {/* 7. Detector Diagnostics / Processing Errors */}
      {hasProcessingErrors && (
        <div className="panel-section diagnostics-panel">
          <div className="diagnostics-panel-header">
            <AlertTriangle size={16} />
            <h4>Vision Detector Diagnostics ({failedDetectors.length} incomplete)</h4>
          </div>
          <div className="diagnostics-list">
            {Object.entries(processingErrors).map(([detKey, errText]) => (
              <div key={detKey} className="diagnostic-item">
                <span className="diagnostic-key">{detKey.replace(/_/g, " ").toUpperCase()}:</span>
                <span className="diagnostic-val">{String(errText)}</span>
              </div>
            ))}
          </div>
          <small className="diagnostics-footnote">
            Detectors with processing errors could not complete evaluation. Their status is reported as unverified rather than clear.
          </small>
        </div>
      )}

      {/* 8. Pipeline Health Collapsible */}
      {detectorStatuses && Object.keys(detectorStatuses).length > 0 && (
        <details className="detector-health-collapsible">
          <summary>Vision Pipeline Detector Health ({Object.keys(detectorStatuses).length} detectors configured)</summary>
          <div className="detector-health-grid">
            {Object.entries(detectorStatuses).map(([name, status]) => (
              <div key={name} className="detector-health-pill">
                <span className="detector-name">{name.replace(/_/g, " ")}:</span>
                <span className={`detector-state state-${status.includes("experimental") ? "experimental" : status}`}>
                  {status}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* 9. Raw AI Debug Output */}
      <details className="api-debug">
        <summary>View Raw AI response JSON</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>

    </div>
  );
}/* =========================
   ANALYTICS
========================= */

function AnalyticsPage() {
  const [alerts, setAlerts] = useState([]);
  const [incidents, setIncidents] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [alertsData, incidentsData] =
        await Promise.all([
          apiRequest("/alerts"),
          apiRequest("/incidents"),
        ]);

      setAlerts(
        Array.isArray(alertsData)
          ? alertsData
          : []
      );

      setIncidents(
        Array.isArray(incidentsData)
          ? incidentsData
          : []
      );

    } catch (err) {
      console.error(err);
      setError(err.message || "Failed to load safety analytics data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const alertTypes = {};

  alerts.forEach((alert) => {
    const key = alert.alert_type || "Other";
    alertTypes[key] = (alertTypes[key] || 0) + 1;
  });

  const incidentTypes = {};

  incidents.forEach((incident) => {
    const key =
      incident.incident_type || "Other";

    incidentTypes[key] =
      (incidentTypes[key] || 0) + 1;
  });

  const alertRows = Object.entries(alertTypes)
    .map(([label, value]) => ({
      label,
      value,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  const incidentRows = Object.entries(
    incidentTypes
  )
    .map(([label, value]) => ({
      label,
      value,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  return (
    <div className="content-page">

      <PageHeading
        title="Safety Analytics"
        description="Operational overview of campus incidents and alerts."
        onRefresh={loadData}
      />

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}


      {loading ? (
        <LoadingState />
      ) : (
        <>
          <div className="stats-grid">

            <StatCard
              title="Total Alerts"
              value={alerts.length}
              icon={Bell}
              tone="blue"
            />

            <StatCard
              title="Active Alerts"
              value={
                alerts.filter(
                  (item) => item.status === "active"
                ).length
              }
              icon={AlertTriangle}
              tone="red"
            />

            <StatCard
              title="Total Incidents"
              value={incidents.length}
              icon={FileText}
              tone="orange"
            />

            <StatCard
              title="Resolved Incidents"
              value={
                incidents.filter(
                  (item) =>
                    item.status === "resolved"
                ).length
              }
              icon={CheckCircle}
              tone="green"
            />

          </div>


          <div className="analytics-grid">

            <AnalyticsBarChart
              title="Alerts by Type"
              rows={alertRows}
            />

            <AnalyticsBarChart
              title="Incidents by Type"
              rows={incidentRows}
            />

          </div>

        </>
      )}

    </div>
  );
}


/* =========================
   AI ASSISTANT
========================= */

function AssistantPage() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text:
        "Hello. I am the CampusGuard AI safety assistant. Ask me about campus safety procedures, emergencies, incidents or restricted areas.",
    },
  ]);

  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);

  async function sendQuestion(event) {
    event?.preventDefault();

    const trimmed = question.trim();

    if (!trimmed || loading) return;

    setMessages((previous) => [
      ...previous,
      {
        role: "user",
        text: trimmed,
      },
    ]);

    setQuestion("");

    try {
      setLoading(true);

      const data = await apiRequest(
        "/assistant/ask",
        {
          method: "POST",
          body: JSON.stringify({
            question: trimmed,
          }),
        }
      );

      const answer =
        data.answer ||
        data.response ||
        data.message ||
        "I could not generate a response.";

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          text: answer,
          sources: Array.isArray(data.sources) ? data.sources : [],
        },
      ]);

    } catch (error) {

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          text:
            error.message ||
            "Unable to connect to the AI assistant.",
        },
      ]);

    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="content-page assistant-page">

      <PageHeading
        title="CampusGuard AI Assistant"
        description="Ask questions about campus safety and emergency procedures."
      />


      <section className="assistant-shell">

        <div className="assistant-header">

          <div className="assistant-avatar">
            <Bot size={23} />
          </div>

          <div>
            <strong>Campus Safety Assistant</strong>

            <span>
              RAG-powered campus knowledge
            </span>
          </div>

          <div className="assistant-online">
            <span className="status-dot online" />
            Online
          </div>

        </div>


        <div className="chat-area">

          {messages.map((message, index) => (

            <div
              key={index}
              className={`chat-message ${
                message.role === "user"
                  ? "user-message"
                  : "assistant-message"
              }`}
            >

              {message.role === "assistant" && (
                <div className="chat-avatar">
                  <Bot size={16} />
                </div>
              )}

              <div className="chat-bubble">
                <div className="chat-bubble-text">{message.text}</div>

                {message.role === "assistant" &&
                  Array.isArray(message.sources) &&
                  message.sources.length > 0 && (
                    <div className="chat-sources">
                      <div className="chat-sources-header">
                        <FileText size={12} />
                        <span>Sources</span>
                      </div>
                      <div className="chat-sources-list">
                        {message.sources.map((source, sIdx) => {
                          const docName =
                            source.file ||
                            source.source ||
                            source.document_name ||
                            source.document;
                          const section = source.section || source.heading;
                          const hasScore =
                            typeof source.score === "number" &&
                            !Number.isNaN(source.score);

                          if (!docName && !section && !hasScore) return null;

                          return (
                            <div key={sIdx} className="chat-source-badge">
                              {docName && (
                                <span className="source-doc">{docName}</span>
                              )}
                              {section && (
                                <span className="source-section">{section}</span>
                              )}
                              {hasScore && (
                                <span
                                  className="source-score"
                                  title="Relevance score"
                                >
                                  Score: {source.score.toFixed(2)}
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
              </div>

            </div>

          ))}

          {loading && (
            <div className="chat-message assistant-message">

              <div className="chat-avatar">
                <Bot size={16} />
              </div>

              <div className="chat-bubble typing">
                Thinking...
              </div>

            </div>
          )}

        </div>


        <form
          className="chat-input-area"
          onSubmit={sendQuestion}
        >

          <MessageSquare size={19} />

          <input
            value={question}
            onChange={(event) =>
              setQuestion(event.target.value)
            }
            placeholder="Ask a campus safety question..."
          />

          <button
            type="submit"
            className="primary-button"
            disabled={loading || !question.trim()}
          >
            Send
          </button>

        </form>

      </section>

    </div>
  );
}


/* =========================
   SOS PAGE
========================= */

function SOSPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadSOS() {
    try {
      setLoading(true);

      const data = await apiRequest("/sos");

      setAlerts(
        Array.isArray(data)
          ? data
          : []
      );

    } catch (err) {
      setError(err.message || "Unable to load SOS history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSOS();
  }, []);

  const [sosLocation, setSosLocation] = useState("Main Campus Library");

  async function sendSOS() {
    if (
      !window.confirm(
        `Are you sure you want to send an emergency SOS alert for location: "${sosLocation}"?`
      )
    ) {
      return;
    }

    try {
      setSending(true);
      setMessage("");
      setError("");

      const data = await apiRequest("/sos", {
        method: "POST",
        body: JSON.stringify({
          location: sosLocation.trim() || "Main Campus",
          description: "Emergency SOS alert triggered by student"
        })
      });

      setMessage(
        data.message ||
        "SOS alert sent successfully."
      );

      await loadSOS();

    } catch (err) {
      setError(
        err.message ||
        "Unable to send SOS alert."
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="content-page">

      <PageHeading
        title="Emergency SOS"
        description="Send an emergency alert to campus security."
      />


      {message && (
        <div className="success-message page-alert">
          <CheckCircle size={18} />
          {message}
        </div>
      )}

      {error && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}


      <section className="sos-page-card">

        <div className="sos-page-icon">
          <Siren size={40} />
        </div>

        <h2>Need immediate help?</h2>

        <p>
          Press the emergency SOS button to notify
          campus security.
        </p>

        <div style={{ maxWidth: "340px", margin: "0 auto 18px", textAlign: "left" }}>
          <label style={{ fontSize: "12px", fontWeight: 600, color: "#475569", display: "block", marginBottom: "6px" }}>
            Select Your Current Campus Location
          </label>
          <select
            style={{ width: "100%", padding: "10px 12px", border: "1px solid #cbd5e1", borderRadius: "8px", fontSize: "13px" }}
            value={sosLocation}
            onChange={(e) => setSosLocation(e.target.value)}
          >
            <option value="Main Campus Library">Main Campus Library</option>
            <option value="Hostel Block A / Dormitories">Hostel Block A / Dormitories</option>
            <option value="Hostel Block B">Hostel Block B</option>
            <option value="Science & Engineering Complex">Science & Engineering Complex</option>
            <option value="Student Activity Center">Student Activity Center</option>
            <option value="Sports Arena / Gym">Sports Arena / Gym</option>
            <option value="Campus Cafeteria">Campus Cafeteria</option>
            <option value="Main Gate / Checkpoint">Main Gate / Checkpoint</option>
          </select>
        </div>

        <button
          className="sos-large-button"
          onClick={sendSOS}
          disabled={sending}
        >
          <Siren size={28} />
          {sending
            ? "Sending Alert..."
            : "SEND EMERGENCY SOS"}
        </button>

      </section>


      <section className="panel">

        <PanelHeader
          icon={Clock}
          title="SOS History"
        />

        {loading ? (
          <LoadingState />
        ) : alerts.length === 0 ? (
          <EmptyState
            icon={Siren}
            title="No SOS alerts"
            text="Your emergency alerts will appear here."
          />
        ) : (
          <div className="activity-list">

            {alerts.map((alert) => (

              <div
                className="activity-item"
                key={alert.id}
              >

                <div className="activity-icon red-icon">
                  <Siren size={17} />
                </div>

                <div className="activity-content">

                  <strong>
                    Emergency SOS
                  </strong>

                  <span>
                    {alert.description}
                  </span>

                  <small>
                    {formatDate(alert.created_at)}
                  </small>

                </div>

                <StatusBadge
                  value={alert.status}
                />

              </div>

            ))}

          </div>
        )}

      </section>

    </div>
  );
}


/* =========================
   SETTINGS
========================= */

function SettingsPage({ user }) {
  const isAdmin = user.role === "admin";
  const [usersList, setUsersList] = useState([]);
  const [camerasList, setCamerasList] = useState([]);
  const [campusOverview, setCampusOverview] = useState(null);
  const [mgmtLoading, setMgmtLoading] = useState(false);
  const [mgmtError, setMgmtError] = useState("");
  const [mgmtSuccess, setMgmtSuccess] = useState("");

  // New user form state
  const [newUserName, setNewUserName] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState("student");

  // New camera form state
  const [newCameraName, setNewCameraName] = useState("");
  const [newCameraLocation, setNewCameraLocation] = useState("");

  async function loadAdminData() {
    if (!isAdmin) return;
    try {
      setMgmtLoading(true);
      setMgmtError("");
      const [uData, cData, rData] = await Promise.all([
        apiRequest("/users").catch(() => []),
        apiRequest("/cameras").catch(() => []),
        apiRequest("/risk/campus-overview").catch(() => null),
      ]);
      setUsersList(Array.isArray(uData) ? uData : []);
      setCamerasList(Array.isArray(cData) ? cData : []);
      setCampusOverview(rData);
    } catch (err) {
      setMgmtError(err.message || "Failed to load management data.");
    } finally {
      setMgmtLoading(false);
    }
  }

  useEffect(() => {
    loadAdminData();
  }, [isAdmin]);

  async function handleCreateUser(e) {
    e.preventDefault();
    if (!newUserName || !newUserEmail || !newUserPassword) return;
    try {
      setMgmtError("");
      await apiRequest("/users", {
        method: "POST",
        body: JSON.stringify({
          name: newUserName,
          email: newUserEmail,
          password: newUserPassword,
          role: newUserRole,
        }),
      });
      setMgmtSuccess("User account created successfully.");
      setNewUserName("");
      setNewUserEmail("");
      setNewUserPassword("");
      await loadAdminData();
    } catch (err) {
      setMgmtError(err.message || "Could not create user.");
    }
  }

  async function handleDeleteUser(userId) {
    if (!window.confirm(`Delete user #${userId}?`)) return;
    try {
      setMgmtError("");
      await apiRequest(`/users/${userId}`, { method: "DELETE" });
      setMgmtSuccess(`User #${userId} deleted successfully.`);
      await loadAdminData();
    } catch (err) {
      setMgmtError(err.message || "Could not delete user.");
    }
  }

  async function handleCreateCamera(e) {
    e.preventDefault();
    if (!newCameraName || !newCameraLocation) return;
    try {
      setMgmtError("");
      await apiRequest("/cameras", {
        method: "POST",
        body: JSON.stringify({
          name: newCameraName,
          location: newCameraLocation,
          status: true,
        }),
      });
      setMgmtSuccess("Camera registered successfully.");
      setNewCameraName("");
      setNewCameraLocation("");
      await loadAdminData();
    } catch (err) {
      setMgmtError(err.message || "Could not register camera.");
    }
  }

  async function handleToggleCamera(cam) {
    try {
      setMgmtError("");
      await apiRequest(`/cameras/${cam.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: !cam.status }),
      });
      await loadAdminData();
    } catch (err) {
      setMgmtError(err.message || "Could not update camera.");
    }
  }

  async function handleDeleteCamera(camId) {
    if (!window.confirm(`Delete camera #${camId}?`)) return;
    try {
      setMgmtError("");
      await apiRequest(`/cameras/${camId}`, { method: "DELETE" });
      setMgmtSuccess(`Camera #${camId} deleted.`);
      await loadAdminData();
    } catch (err) {
      setMgmtError(err.message || "Could not delete camera.");
    }
  }

  return (
    <div className="content-page">

      <PageHeading
        title="Settings & Administration"
        description="Account overview and system configuration."
      />

      {mgmtSuccess && (
        <div className="success-message page-alert">
          <CheckCircle size={18} />
          {mgmtSuccess}
        </div>
      )}

      {mgmtError && (
        <div className="error-message page-alert">
          <AlertTriangle size={18} />
          {mgmtError}
        </div>
      )}

      {/* Multi-Signal Campus Risk Overview for Admins */}
      {isAdmin && campusOverview && (
        <div className="campus-overview-card">
          <div className="campus-overview-header">
            <div>
              <h3 style={{ margin: 0, fontSize: "16px", color: "#f8fafc" }}>Multi-Signal Campus Safety Overview</h3>
              <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#94a3b8" }}>Real-time aggregate risk across cameras, incidents, SOS, and hours.</p>
            </div>
            <StatusBadge value={campusOverview.risk_level} />
          </div>

          <div className="campus-overview-stats">
            <div className="campus-stat-box">
              <span>Safety Index</span>
              <strong style={{ color: "#38bdf8" }}>{campusOverview.safety_index}%</strong>
            </div>
            <div className="campus-stat-box">
              <span>Risk Score</span>
              <strong style={{ color: campusOverview.risk_score > 60 ? "#ef4444" : "#10b981" }}>{campusOverview.risk_score} / 100</strong>
            </div>
            <div className="campus-stat-box">
              <span>Active SOS Alerts</span>
              <strong style={{ color: "#ef4444" }}>{campusOverview.active_sos_count}</strong>
            </div>
            <div className="campus-stat-box">
              <span>Critical Alerts</span>
              <strong>{campusOverview.critical_alerts_count}</strong>
            </div>
            <div className="campus-stat-box">
              <span>Active Cameras</span>
              <strong style={{ color: "#10b981" }}>{campusOverview.active_cameras} / {campusOverview.total_cameras}</strong>
            </div>
          </div>

          {campusOverview.contributing_signals && campusOverview.contributing_signals.length > 0 && (
            <div className="signals-list">
              {campusOverview.contributing_signals.map((sig, idx) => (
                <span key={idx} className="signal-pill">• {sig}</span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="settings-grid">

        <section className="panel">

          <PanelHeader
            icon={User}
            title="Account Information"
          />

          <div className="settings-list">

            <SettingRow
              label="Name"
              value={user.name}
            />

            <SettingRow
              label="Email"
              value={user.email}
            />

            <SettingRow
              label="Role"
              value={capitalize(user.role)}
            />

            <SettingRow
              label="User ID"
              value={`#${user.user_id}`}
            />

          </div>

        </section>


        <section className="panel">

          <PanelHeader
            icon={Shield}
            title="Platform Status"
          />

          <div className="settings-list">

            <SettingStatus
              label="FastAPI Backend"
              status="Connected"
            />

            <SettingStatus
              label="Database"
              status="Connected"
            />

            <SettingStatus
              label="Authentication"
              status="Active"
            />

            <SettingStatus
              label="AI Services"
              status="Active"
            />

          </div>

        </section>

      </div>

      {/* Admin User Management Section */}
      {isAdmin && (
        <section className="panel admin-mgmt-section">
          <PanelHeader
            icon={Users}
            title="User Management"
            action={mgmtLoading ? "Loading..." : "Refresh"}
            onAction={loadAdminData}
          />

          <div style={{ padding: "16px 20px" }}>
            <form onSubmit={handleCreateUser} className="admin-form-inline">
              <input
                type="text"
                placeholder="Full Name"
                value={newUserName}
                onChange={(e) => setNewUserName(e.target.value)}
                required
              />
              <input
                type="email"
                placeholder="Email Address"
                value={newUserEmail}
                onChange={(e) => setNewUserEmail(e.target.value)}
                required
              />
              <input
                type="password"
                placeholder="Password"
                value={newUserPassword}
                onChange={(e) => setNewUserPassword(e.target.value)}
                required
              />
              <select
                value={newUserRole}
                onChange={(e) => setNewUserRole(e.target.value)}
              >
                <option value="student">Student</option>
                <option value="security">Security</option>
                <option value="admin">Admin</option>
              </select>
              <button type="submit" className="primary-button" style={{ height: "35px", padding: "0 14px" }}>
                + Add User
              </button>
            </form>

            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {usersList.map((u) => (
                    <tr key={u.id}>
                      <td>#{u.id}</td>
                      <td><strong>{u.name}</strong></td>
                      <td>{u.email}</td>
                      <td><StatusBadge value={u.role} /></td>
                      <td>
                        {u.id !== user.user_id && (
                          <button
                            className="small-button danger-button"
                            onClick={() => handleDeleteUser(u.id)}
                            style={{ background: "#fee2e2", color: "#dc2626", border: "1px solid #fca5a5" }}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* Admin Camera Management Section */}
      {isAdmin && (
        <section className="panel admin-mgmt-section">
          <PanelHeader
            icon={Camera}
            title="Camera Management"
            action={mgmtLoading ? "Loading..." : "Refresh"}
            onAction={loadAdminData}
          />

          <div style={{ padding: "16px 20px" }}>
            <form onSubmit={handleCreateCamera} className="admin-form-inline">
              <input
                type="text"
                placeholder="Camera Name (e.g. Science Corridor Cam)"
                value={newCameraName}
                onChange={(e) => setNewCameraName(e.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Campus Location (e.g. Science Block 1st Floor)"
                value={newCameraLocation}
                onChange={(e) => setNewCameraLocation(e.target.value)}
                required
              />
              <button type="submit" className="primary-button" style={{ height: "35px", padding: "0 14px" }}>
                + Register Camera
              </button>
            </form>

            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Location</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {camerasList.map((cam) => (
                    <tr key={cam.id}>
                      <td>#{cam.id}</td>
                      <td><strong>{cam.name}</strong></td>
                      <td>{cam.location}</td>
                      <td>
                        <StatusBadge value={cam.status ? "active" : "inactive"} />
                      </td>
                      <td>
                        <div className="table-actions">
                          <button
                            className="small-button"
                            onClick={() => handleToggleCamera(cam)}
                          >
                            {cam.status ? "Deactivate" : "Activate"}
                          </button>
                          <button
                            className="small-button danger-button"
                            onClick={() => handleDeleteCamera(cam.id)}
                            style={{ background: "#fee2e2", color: "#dc2626", border: "1px solid #fca5a5" }}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

    </div>
  );
}


/* =========================
   COMPONENTS
========================= */

function StatCard({
  title,
  value,
  icon: Icon,
  tone = "blue",
}) {
  return (
    <div className="stat-card">

      <div className={`stat-icon ${tone}`}>
        <Icon size={20} />
      </div>

      <div className="stat-content">

        <span>{title}</span>

        <strong>{value}</strong>

      </div>

    </div>
  );
}


function PanelHeader({
  icon: Icon,
  title,
  action,
  onAction,
}) {
  return (
    <div className="panel-header">

      <div className="panel-title">

        <div className="panel-title-icon">
          <Icon size={18} />
        </div>

        <h3>{title}</h3>

      </div>

      {action && (
        <button
          className="panel-action"
          onClick={onAction}
        >
          {action}
          <ChevronRight size={15} />
        </button>
      )}

    </div>
  );
}


function PageHeading({
  title,
  description,
  onRefresh,
  action,
  onAction,
}) {
  return (
    <div className="page-heading-row">

      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>

      <div className="heading-actions">
        {action && onAction && (
          <button
            className="primary-button"
            onClick={onAction}
          >
            {action}
          </button>
        )}

        {onRefresh && (
          <button
            className="refresh-button"
            onClick={onRefresh}
          >
            <RefreshCw size={17} />
            Refresh
          </button>
        )}
      </div>

    </div>
  );
}


function StatusBadge({ value }) {
  const text = String(value || "unknown");

  return (
    <span
      className={`status-badge ${getSeverityClass(
        text
      )}`}
    >
      {capitalize(text)}
    </span>
  );
}


function LoadingState() {
  return (
    <div className="loading-state">
      <div className="loading-spinner" />
      <span>Loading data...</span>
    </div>
  );
}


function EmptyState({
  icon: Icon,
  title,
  text,
}) {
  return (
    <div className="empty-state">

      <div className="empty-icon">
        <Icon size={24} />
      </div>

      <strong>{title}</strong>

      <span>{text}</span>

    </div>
  );
}


function AnalyticsBarChart({
  title,
  rows,
}) {
  const max =
    Math.max(
      ...(rows.map((row) => row.value)),
      1
    );

  return (
    <section className="panel">

      <PanelHeader
        icon={BarChart3}
        title={title}
      />

      {rows.length === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="No data"
          text="There is not enough data to display this chart."
        />
      ) : (
        <div className="analytics-bars">

          {rows.map((row) => {

            const percentage =
              (row.value / max) * 100;

            return (
              <div
                className="analytics-row"
                key={row.label}
              >

                <div className="analytics-label">
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                </div>

                <div className="analytics-track">
                  <div
                    className="analytics-fill"
                    style={{
                      width: `${percentage}%`,
                    }}
                  />
                </div>

              </div>
            );

          })}

        </div>
      )}

    </section>
  );
}


function SystemStatus({
  label,
  status,
}) {
  return (
    <div className="system-status-row">

      <span>{label}</span>

      <div className="system-status-value">
        <span className="status-dot online" />
        {status}
      </div>

    </div>
  );
}


function SettingRow({
  label,
  value,
}) {
  return (
    <div className="setting-row">

      <span>{label}</span>

      <strong>{value || "-"}</strong>

    </div>
  );
}


function SettingStatus({
  label,
  status,
}) {
  return (
    <div className="setting-row">

      <span>{label}</span>

      <div className="setting-status">
        <span className="status-dot online" />
        {status}
      </div>

    </div>
  );
}


/* =========================
   HELPERS
========================= */

function capitalize(value) {
  if (!value) return "";

  return String(value)
    .charAt(0)
    .toUpperCase() +
    String(value).slice(1);
}


function getPageTitle(page, role) {
  if (page === "dashboard") {
    if (role === "student") {
      return "Student Dashboard";
    }

    if (role === "security") {
      return "Security Operations";
    }

    return "Administration";
  }

  const titles = {
    incidents: "Incident Management",
    alerts: "Security Alerts",
    cctv: "CCTV Intelligence",
    analytics: "Safety Analytics",
    assistant: "AI Assistant",
    settings: "Settings",
    sos: "Emergency SOS",
  };

  return titles[page] || "CampusGuard AI";
}


function getRiskTextClass(level) {
  const text = String(level || "").toLowerCase();

  if (text === "high" || text === "critical") {
    return "risk-high";
  }

  if (text === "medium" || text === "caution") {
    return "risk-medium";
  }

  if (text === "low" || text === "normal") {
    return "risk-low";
  }

  return "";
}

