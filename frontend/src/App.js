import React, { useEffect, useState } from 'react';
import {
  Container, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Switch, Box, Button
} from '@mui/material';
import axios from 'axios';

const API = process.env.REACT_APP_API_URL || 'http://localhost:5000/api/dashboard';

function App() {
  const [data, setData] = useState([]);
  const [darkMode, setDarkMode] = useState(false);

  const fetchData = () => {
    console.log('Fetching data from:', API);
    axios.get(`${API}?t=${new Date().getTime()}`, {
      headers: { 'Cache-Control': 'no-cache' }
    })
      .then(res => {
        console.log("Raw API response:", res.data);
        const processedData = res.data.map(user => ({
          ...user,
          app_usage: Array.isArray(user.app_usage) ? user.app_usage : []
        }));
        console.log("Processed data:", processedData);
        setData(processedData);
      })
      .catch(err => {
        console.error("API fetch error:", err);
        console.error("Error details:", err.response?.data);
      });
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // auto-refresh every 30 sec
    return () => clearInterval(interval);
  }, []);

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

  const themeStyles = {
    backgroundColor: darkMode ? '#121212' : '#f4f6f8',
    color: darkMode ? '#fff' : '#000',
    minHeight: '100vh',
    paddingTop: '2rem'
  };

  return (
    <Box sx={themeStyles}>
      <Container maxWidth="lg">
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
          <Typography variant="h4">👨‍💻 WFH Monitoring Dashboard</Typography>
          <Box display="flex" alignItems="center">
            <Typography variant="body1" sx={{ mr: 1 }}>Dark Mode</Typography>
            <Switch checked={darkMode} onChange={() => setDarkMode(!darkMode)} />
          </Box>
        </Box>

        <TableContainer component={Paper} elevation={3}>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: darkMode ? '#333' : '#1976d2' }}>
                {[
                  'User',
                  'Channel',
                  'Screen Shared',
                  'Last Update',
                  'Active App',
                  'Active Apps',
                  'Screen Share Time',
                  'Total Idle Time',
                  'Total Working Hours',
                  'App Usage', // New column header
                  'Actions'
                ].map((head, idx) => (
                  <TableCell key={idx} sx={{ color: '#fff', fontWeight: 'bold' }}>{head}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {data.length > 0 ? data.map((u, i) => (
                <TableRow 
                  key={i} 
                  sx={{ 
                    backgroundColor: u.screen_shared ? '#e8f5e9' : 'inherit',
                    '&:hover': {
                      backgroundColor: darkMode ? '#2c2c2c' : '#f5f5f5'
                    }
                  }}
                >
                  <TableCell>{u.username}</TableCell>
                  <TableCell>{u.channel || 'N/A'}</TableCell>
                  <TableCell>{u.screen_shared ? '✅' : '❌'}</TableCell>
                  <TableCell>
                    {u.timestamp && !isNaN(new Date(u.timestamp))
                      ? new Date(u.timestamp).toLocaleString()
                      : 'N/A'}
                  </TableCell>
                  <TableCell sx={{ color: '#2e7d32', fontWeight: 'bold' }}>
                    {u.active_app || 'Unknown'}
                  </TableCell>
                  <TableCell>{u.active_apps?.join(', ') || 'None'}</TableCell>
                  <TableCell>{u.screen_share_time ? `${Math.floor(u.screen_share_time / 60)} mins` : '0 mins'}</TableCell>
                  <TableCell>{u.total_idle_time ? `${u.total_idle_time} mins` : '0 mins'}</TableCell>
                  <TableCell>{u.total_working_hours ? `${Math.floor(u.total_working_hours)} hrs` : '0 hrs'}</TableCell>
                  <TableCell sx={{ minWidth: 250 }}>
                    {renderAppUsage(u.app_usage)}
                  </TableCell>
                  <TableCell>
                    <Button 
                      variant="contained" 
                      size="small"
                      onClick={() => handleViewSummary(u.username)}
                      sx={{ 
                        textTransform: 'none',
                        backgroundColor: darkMode ? '#333' : '#1976d2' 
                      }}
                    >
                      View Summary
                    </Button>
                  </TableCell>
                </TableRow>
              )) : (
                <TableRow>
                  <TableCell colSpan={11} align="center" sx={{ py: 3 }}>
                    <Typography variant="body1" color="text.secondary">
                      No user activity available yet.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Container>
    </Box>
  );
}

export default App;
