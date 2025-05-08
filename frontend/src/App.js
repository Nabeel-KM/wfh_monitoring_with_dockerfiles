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
    axios.get(`${API}?t=${new Date().getTime()}`, { headers: { 'Cache-Control': 'no-cache' } })
      .then(res => {
        console.log("Fetched data:", res.data); // Debug log
        setData(res.data);
      })
      .catch(err => console.error("API fetch error:", err));
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
                  'Total Working Hours', // New column header
                  'Actions'
                ].map((head, idx) => (
                  <TableCell key={idx} sx={{ color: '#fff', fontWeight: 'bold' }}>{head}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {data.length > 0 ? data.map((u, i) => (
                <TableRow key={i} sx={{ backgroundColor: u.screen_shared ? '#e8f5e9' : 'inherit' }}>
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
                  <TableCell>{u.total_working_hours ? `${Math.floor(u.total_working_hours / 3600)} hrs` : '0 hrs'}</TableCell> {/* New column */}
                  <TableCell>
                    <Button onClick={() => handleViewSummary(u.username)}>View Summary</Button>
                  </TableCell>
                </TableRow>
              )) : (
                <TableRow>
                  <TableCell colSpan={10} align="center" sx={{ py: 3 }}>
                    No user activity available yet.
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
