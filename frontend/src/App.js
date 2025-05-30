import React, { useEffect, useState, useRef } from 'react';
import {
  Container, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Switch, Box, Button, CircularProgress
} from '@mui/material';
import axios from 'axios';
import { createTheme, ThemeProvider, useTheme } from '@mui/material/styles';
import { BrowserRouter as Router, Route, Routes, Link, useNavigate } from 'react-router-dom';

const API = process.env.REACT_APP_API_URL || 'https://api-wfh.kryptomind.net/api/dashboard';
const HISTORY_API = process.env.REACT_APP_HISTORY_API_URL || 'https://api-wfh.kryptomind.net/api/history';
const S3_BUCKET = process.env.REACT_APP_S3_BUCKET;
const S3_REGION = process.env.REACT_APP_S3_REGION;

function getS3ScreenshotUrls(username, date, times) {
  if (!S3_BUCKET || !S3_REGION) return [];
  return times.map(timeStr => {
    // Convert timeStr from HH-MM-SS to HH-MM format for S3 path
    const [hours, minutes] = timeStr.split('-');
    return `https://${S3_BUCKET}.s3.${S3_REGION}.amazonaws.com/${username}/${date}/screenshot-${hours}-${minutes}-59.png`;
  });
}

function getScreenshotTimesForToday() {
  // Generate times every 2 minutes from 09:00 to 18:00
  const times = [];
  for (let h = 9; h <= 18; h++) {
    for (let m = 0; m < 60; m += 2) {
      times.push(`${String(h).padStart(2, '0')}-${String(m).padStart(2, '0')}-00`);
    }
  }
  return times;
}

function ScreenshotsModal({ open, onClose, username, date }) {
  const [screenshots, setScreenshots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open && username && date) {
      setLoading(true);
      setError(null);
      // Use the actual API endpoint instead of relative path
      axios.get(`https://api-wfh.kryptomind.net/api/screenshots?username=${username}&date=${date}`)
        .then(response => {
          if (response.data && response.data.screenshots) {
            // Map the response data to extract just the URLs and keys
            const screenshotData = response.data.screenshots.map(screenshot => ({
              url: screenshot.url,
              key: screenshot.key,
              timestamp: new Date(screenshot.last_modified).toLocaleTimeString()
            }));
            setScreenshots(screenshotData);
          } else {
            setScreenshots([]);
          }
        })
        .catch(err => {
          console.error('Error fetching screenshots:', err);
          setError('Failed to load screenshots');
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [open, username, date]);

  return open ? (
    <Box sx={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', bgcolor: 'rgba(0,0,0,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}>
      <Box sx={{ bgcolor: 'background.paper', borderRadius: 3, p: 3, minWidth: { xs: 280, sm: 400 }, maxWidth: '90vw', width: '100%', maxHeight: '90vh', overflowY: 'auto', boxShadow: 6 }}>
        <Typography variant="h6" mb={2} fontWeight={700}>Screenshots for {username} ({date})</Typography>
        
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Typography color="error" sx={{ p: 2 }}>{error}</Typography>
        ) : screenshots.length > 0 ? (
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 2 }}>
            {screenshots.map((screenshot, idx) => (
              <Box key={idx} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <a href={screenshot.url} target="_blank" rel="noopener noreferrer">
                  <img 
                    src={screenshot.url} 
                    alt={`Screenshot at ${screenshot.timestamp}`}
                    style={{ 
                      width: '100%',
                      height: '150px',
                      objectFit: 'cover',
                      borderRadius: 4,
                      border: '1px solid #ccc'
                    }}
                  />
                </a>
                <Typography variant="caption" sx={{ mt: 1 }}>
                  {screenshot.timestamp}
                </Typography>
              </Box>
            ))}
          </Box>
        ) : (
          <Typography sx={{ p: 2 }}>No screenshots available for this date.</Typography>
        )}
        
        <Button onClick={onClose} sx={{ mt: 2 }} variant="contained">Close</Button>
      </Box>
    </Box>
  ) : null;
}

function UserDetailsPage({ username }) {
  // Scaffold: fetch and display /api/history and screenshot galleries for each day
  // ... implement as needed ...
  return <Box p={4}><Typography variant="h5">User Details for {username}</Typography></Box>;
}

function App() {
  const [data, setData] = useState([]);
  const [darkMode, setDarkMode] = useState(false);
  const [history, setHistory] = useState({});
  const [historyUser, setHistoryUser] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [screenshotsOpen, setScreenshotsOpen] = useState(false);
  const [screenshotsUser, setScreenshotsUser] = useState(null);
  const [screenshotsDate, setScreenshotsDate] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const fetchTimeoutRef = useRef(null);
  const isMountedRef = useRef(true);

  const polishedTheme = createTheme({
    palette: {
      mode: darkMode ? 'dark' : 'light',
      primary: { main: '#1976d2' },
      secondary: { main: '#2e7d32' },
      background: {
        default: darkMode ? '#181c20' : '#f4f6f8',
        paper: darkMode ? '#23272b' : '#fff',
      },
    },
    typography: {
      fontFamily: 'Inter, Roboto, Arial, sans-serif',
      fontWeightMedium: 600,
    },
    components: {
      MuiTableCell: {
        styleOverrides: {
          head: {
            fontWeight: 700,
            position: 'sticky',
            top: 0,
            zIndex: 2,
            backgroundColor: darkMode ? '#23272b' : '#1976d2',
            color: '#fff',
          },
          body: {
            fontSize: '1rem',
          },
        },
      },
      MuiTableRow: {
        styleOverrides: {
          root: {
            transition: 'background 0.2s',
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: 12,
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            fontWeight: 600,
          },
        },
      },
    },
  });

  const fetchData = async () => {
    if (isLoading || !isMountedRef.current) return;
    
    try {
      setIsLoading(true);
      const res = await axios.get(`${API}?t=${new Date().getTime()}`, {
        headers: { 'Cache-Control': 'no-cache' }
      });
      
      if (isMountedRef.current && res.data && Array.isArray(res.data.data)) {
        const processedData = res.data.data.map(user => ({
          ...user,
          app_usage: Array.isArray(user.app_usage) ? user.app_usage : []
        }));
        setData(processedData);
      }
    } catch (err) {
      console.error("API fetch error:", err);
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    
    // Initial fetch
    fetchData();
    
    // Set up auto-refresh
    const intervalId = setInterval(() => {
      if (isMountedRef.current && !isLoading) {
        fetchData();
      }
    }, 30000);
    
    // Cleanup function
    return () => {
      isMountedRef.current = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, []); // Empty dependency array

  const handleViewSummary = (username) => {
    const userSummary = data.find((u) => u.username === username)?.daily_summaries || [];
    alert(`Daily Summary for ${username}:\n` + userSummary.map(s => `Date: ${s.date}, Screen Share Time: ${Math.floor(s.total_screen_share_time / 60)} mins`).join('\n'));
  };

  const formatTime = (minutes) => {
    if (!minutes) return '0m';
    
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = Math.round(minutes % 60);
    
    if (hours > 0) {
      return `${hours}h ${remainingMinutes}m`;
    }
    return `${remainingMinutes}m`;
  };

  const renderAppUsage = (appUsage) => {
    if (!appUsage || !Array.isArray(appUsage) || appUsage.length === 0) {
      return 'No data';
    }

    // Sort apps by total time
    const sortedApps = [...appUsage].sort((a, b) => b.total_time - a.total_time);

    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {sortedApps.map((app, index) => (
          <Box 
            key={index}
            sx={{ 
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              bgcolor: 'rgba(25, 118, 210, 0.08)',
              p: 0.5,
              borderRadius: 1,
              '&:hover': {
                bgcolor: 'rgba(25, 118, 210, 0.12)'
              }
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 'medium' }}>
              {app.app_name}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {formatTime(app.total_time)}
            </Typography>
          </Box>
        ))}
      </Box>
    );
  };

  const handleViewHistory = async (username) => {
    setHistoryUser(username);
    setShowHistory(true);
    try {
      const res = await axios.get(`${HISTORY_API}?username=${username}&days=7`);
      setHistory(res.data[0] || {});
    } catch (err) {
      setHistory({ error: 'Failed to fetch history' });
    }
  };

  const closeHistory = () => {
    setShowHistory(false);
    setHistoryUser(null);
    setHistory({});
  };

  return (
    <ThemeProvider theme={polishedTheme}>
      <Routes>
        <Route path="/" element={
          <Box sx={{ backgroundColor: 'background.default', color: 'text.primary', minHeight: '100vh', pt: 4 }}>
            <Container maxWidth="lg">
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h4" fontWeight={700}>👨‍💻 WFH Monitoring Dashboard</Typography>
                <Box display="flex" alignItems="center">
                  <Typography variant="body1" sx={{ mr: 1 }}>Dark Mode</Typography>
                  <Switch checked={darkMode} onChange={() => setDarkMode(!darkMode)} />
                </Box>
              </Box>
              <TableContainer component={Paper} elevation={3} sx={{ maxHeight: 600 }}>
                <Table stickyHeader>
                  <TableHead>
                    <TableRow sx={{ backgroundColor: darkMode ? '#333' : '#1976d2' }}>
                      {[ 'User', 'Channel', 'Active App', 'Active Apps', 'Active Time', 'Idle Time', 'Screen Shared', 'Screen Share Time', 'Most Used App', 'App Usage', 'Screenshots', 'Actions' ].map((head, idx) => (
                        <TableCell key={idx} sx={{ color: '#fff', fontWeight: 'bold' }}>{head}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.length > 0 ? data.map((u, i) => (
                      <TableRow key={i} sx={{ backgroundColor: u.screen_shared ? '#e8f5e9' : 'inherit', '&:hover': { backgroundColor: darkMode ? '#2c2c2c' : '#f5f5f5' } }}>
                        <TableCell>
                          <Link to={`/user/${u.username}`} style={{ color: '#1976d2', textDecoration: 'underline', cursor: 'pointer' }}>{u.username}</Link>
                        </TableCell>
                        <TableCell>{u.channel || 'N/A'}</TableCell>
                        <TableCell sx={{ color: '#2e7d32', fontWeight: 'bold' }}>{u.active_app || 'Unknown'}</TableCell>
                        <TableCell>{u.active_apps?.join(', ') || 'None'}</TableCell>
                        <TableCell>{u.total_active_time ? `${u.total_active_time} mins` : '0 mins'}</TableCell>
                        <TableCell>{u.total_idle_time ? `${u.total_idle_time} mins` : '0 mins'}</TableCell>
                        <TableCell>{u.screen_shared ? '✅' : '❌'}</TableCell>
                        <TableCell>{u.screen_share_time ? `${Math.floor(u.screen_share_time / 60)} mins` : '0 mins'}</TableCell>
                        <TableCell>{u.most_used_app ? `${u.most_used_app} (${u.most_used_app_time}m)` : 'N/A'}</TableCell>
                        <TableCell sx={{ minWidth: 250 }}>{renderAppUsage(u.app_usage)}</TableCell>
                        <TableCell>
                          <Button variant="outlined" size="small" onClick={() => { setScreenshotsUser(u.username); setScreenshotsDate(new Date().toISOString().slice(0,10)); setScreenshotsOpen(true); }} sx={{ textTransform: 'none', borderColor: '#1976d2', color: '#1976d2' }}>View</Button>
                        </TableCell>
                        <TableCell>
                          <Button variant="contained" size="small" onClick={() => handleViewSummary(u.username)} sx={{ textTransform: 'none', backgroundColor: darkMode ? '#333' : '#1976d2', mb: 1 }}>View Summary</Button>
                          <Button variant="outlined" size="small" onClick={() => handleViewHistory(u.username)} sx={{ textTransform: 'none', borderColor: '#1976d2', color: '#1976d2' }}>History</Button>
                        </TableCell>
                      </TableRow>
                    )) : (
                      <TableRow>
                        <TableCell colSpan={12} align="center" sx={{ py: 3 }}>
                          <Typography variant="body1" color="text.secondary">No user activity available yet.</Typography>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </Container>
            <ScreenshotsModal open={screenshotsOpen} onClose={() => setScreenshotsOpen(false)} username={screenshotsUser} date={screenshotsDate} />
          </Box>
        } />
        <Route path="/user/:username" element={<UserDetailsPage />} />
      </Routes>
      {showHistory && (
        <Box sx={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', bgcolor: 'rgba(0,0,0,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}>
          <Box sx={{ bgcolor: 'background.paper', borderRadius: 3, p: 3, minWidth: { xs: 280, sm: 400 }, maxWidth: 600, width: '100%', maxHeight: '80vh', overflowY: 'auto', boxShadow: 6 }}>
            <Typography variant="h6" mb={2} fontWeight={700}>History for {historyUser}</Typography>
            {history.days && history.days.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Active Time (min)</TableCell>
                    <TableCell>Session Time (hr)</TableCell>
                    <TableCell>Idle Time (min)</TableCell>
                    <TableCell>First Activity</TableCell>
                    <TableCell>Last Activity</TableCell>
                    <TableCell>Most Used App</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {history.days.map((d, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{d.date}</TableCell>
                      <TableCell>{d.total_active_time}</TableCell>
                      <TableCell>{d.total_session_time}</TableCell>
                      <TableCell>{d.total_idle_time}</TableCell>
                      <TableCell>{d.first_activity ? new Date(d.first_activity).toLocaleTimeString() : 'N/A'}</TableCell>
                      <TableCell>{d.last_activity ? new Date(d.last_activity).toLocaleTimeString() : 'N/A'}</TableCell>
                      <TableCell>{d.most_used_app ? `${d.most_used_app} (${d.most_used_app_time}m)` : 'N/A'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <Typography>No history data available.</Typography>
            )}
            <Button onClick={closeHistory} sx={{ mt: 2 }} variant="contained">Close</Button>
          </Box>
        </Box>
      )}
    </ThemeProvider>
  );
}

export default App;
