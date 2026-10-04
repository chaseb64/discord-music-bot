/**
 * Aether Beats - Discord Music Command Center
 * Real-time WebSocket Client & Interactive Dashboard Controller
 */

(function () {
  'use strict';

  // --- State Variables ---
  let currentGuildId = null;
  let allGuilds = [];
  let currentTrackStartTime = null;
  let currentTrackDuration = 0;
  let isPlaying = false;
  let isPaused = false;
  let ws = null;
  let reconnectTimeout = null;
  let progressInterval = null;

  // --- DOM Elements ---
  const guildSelect = document.getElementById('guildSelect');
  const connectionBadge = document.getElementById('connectionBadge');
  const connectionText = document.getElementById('connectionText');

  const artWrap = document.getElementById('artWrap');
  const albumArt = document.getElementById('albumArt');
  const statusBadge = document.getElementById('statusBadge');
  const sourceBadge = document.getElementById('sourceBadge');
  const trackTitle = document.getElementById('trackTitle');
  const trackArtist = document.getElementById('trackArtist');

  const equalizerCanvas = document.getElementById('equalizerCanvas');
  const vCtx = equalizerCanvas ? equalizerCanvas.getContext('2d') : null;

  const progressBarFill = document.getElementById('progressBarFill');
  const currentTimeEl = document.getElementById('currentTime');
  const totalDurationEl = document.getElementById('totalDuration');

  const btnPrev = document.getElementById('btnPrev');
  const btnPlayPause = document.getElementById('btnPlayPause');
  const playPauseIcon = document.getElementById('playPauseIcon');
  const btnSkip = document.getElementById('btnSkip');
  const btnStop = document.getElementById('btnStop');

  const volumeSlider = document.getElementById('volumeSlider');
  const volumeLabel = document.getElementById('volumeLabel');
  const volIcon = document.getElementById('volIcon');

  const searchForm = document.getElementById('searchForm');
  const searchInput = document.getElementById('searchInput');
  const btnAddTrack = document.getElementById('btnAddTrack');

  const queueList = document.getElementById('queueList');
  const queueEmpty = document.getElementById('queueEmpty');
  const queueCount = document.getElementById('queueCount');

  const statCpu = document.getElementById('statCpu');
  const barCpu = document.getElementById('barCpu');
  const statRam = document.getElementById('statRam');
  const barRam = document.getElementById('barRam');
  const statUptime = document.getElementById('statUptime');
  const statPing = document.getElementById('statPing');
  const statStreams = document.getElementById('statStreams');
  const statGuilds = document.getElementById('statGuilds');

  const channelPill = document.getElementById('channelPill');
  const channelName = document.getElementById('channelName');
  const listenerCount = document.getElementById('listenerCount');

  const toastContainer = document.getElementById('toastContainer');

  const ICON_PLAY = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
  const ICON_PAUSE = '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>';

  // --- WebSocket Connection ---
  function connectWebSocket() {
    if (ws) {
      try { ws.close(); } catch (e) {}
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws`;

    setConnectionStatus('connecting', 'CONNECTING...');

    ws = new WebSocket(wsUrl);

    ws.onopen = function () {
      setConnectionStatus('online', 'CONNECTED');
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }
    };

    ws.onmessage = function (event) {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'status_update' || message.type === 'STATE_UPDATE') {
          handleStateUpdate(message.data || message);
        }
      } catch (err) {
        console.error('Error parsing state update:', err);
      }
    };

    ws.onclose = function () {
      setConnectionStatus('offline', 'OFFLINE');
      if (!reconnectTimeout) {
        reconnectTimeout = setTimeout(connectWebSocket, 3000);
      }
    };

    ws.onerror = function () {
      setConnectionStatus('offline', 'ERROR');
    };
  }

  function setConnectionStatus(status, text) {
    if (connectionText) connectionText.textContent = text;
    if (connectionBadge) {
      connectionBadge.className = `status-badge ${status}`;
    }
  }

  // --- State Handler ---
  function handleStateUpdate(data) {
    allGuilds = data.guilds || [];

    // Vitals
    const stats = data.stats || data.metrics;
    if (stats) {
      updateVitals(stats);
    }

    // Guilds Dropdown
    updateGuildsDropdown(allGuilds);

    // Active Guild Playback
    if (currentGuildId) {
      const activeGuild = allGuilds.find(g => (g.id === currentGuildId || g.guild_id === currentGuildId));
      if (activeGuild) {
        renderGuildPlayback(activeGuild);
      } else {
        renderNoGuildSelected();
      }
    } else if (allGuilds.length > 0) {
      const playingGuild = allGuilds.find(g => g.is_playing) || allGuilds[0];
      currentGuildId = playingGuild.id || playingGuild.guild_id;
      if (guildSelect) guildSelect.value = currentGuildId;
      renderGuildPlayback(playingGuild);
    } else {
      renderNoGuildSelected();
    }
  }

  function updateGuildsDropdown(guilds) {
    if (!guildSelect) return;

    const previousVal = guildSelect.value || currentGuildId;
    let html = '';

    if (guilds.length === 0) {
      html = '<option value="" disabled selected>No Discord servers joined</option>';
    } else {
      guilds.forEach(g => {
        const gid = g.id || g.guild_id;
        const gname = g.name || g.guild_name || 'Server';
        const playingTag = g.is_playing ? ' 🎵' : '';
        html += `<option value="${gid}">${escapeHtml(gname)}${playingTag}</option>`;
      });
    }

    if (guildSelect.innerHTML !== html) {
      guildSelect.innerHTML = html;
      if (previousVal && guilds.some(g => (g.id === previousVal || g.guild_id === previousVal))) {
        guildSelect.value = previousVal;
      } else if (guilds.length > 0) {
        const firstId = guilds[0].id || guilds[0].guild_id;
        guildSelect.value = firstId;
        currentGuildId = firstId;
      }
    }
  }

  function renderGuildPlayback(guild) {
    isPlaying = guild.is_playing || false;
    isPaused = guild.is_paused || false;
    const track = guild.current_track;

    // Status Badge & Disc Spin Animation
    if (isPlaying && !isPaused) {
      if (statusBadge) {
        statusBadge.textContent = 'PLAYING';
        statusBadge.style.background = 'rgba(6, 182, 212, 0.2)';
        statusBadge.style.color = '#00f0ff';
        statusBadge.style.borderColor = 'rgba(6, 182, 212, 0.4)';
      }
      if (artWrap) artWrap.classList.add('is-playing');
      if (playPauseIcon) playPauseIcon.innerHTML = ICON_PAUSE;
    } else if (isPlaying && isPaused) {
      if (statusBadge) {
        statusBadge.textContent = 'PAUSED';
        statusBadge.style.background = 'rgba(234, 179, 8, 0.2)';
        statusBadge.style.color = '#eab308';
        statusBadge.style.borderColor = 'rgba(234, 179, 8, 0.4)';
      }
      if (artWrap) artWrap.classList.remove('is-playing');
      if (playPauseIcon) playPauseIcon.innerHTML = ICON_PLAY;
    } else {
      if (statusBadge) {
        statusBadge.textContent = 'IDLE';
        statusBadge.style.background = 'rgba(88, 101, 242, 0.15)';
        statusBadge.style.color = '#A5B4FC';
        statusBadge.style.borderColor = 'rgba(88, 101, 242, 0.3)';
      }
      if (artWrap) artWrap.classList.remove('is-playing');
      if (playPauseIcon) playPauseIcon.innerHTML = ICON_PLAY;
    }

    // Voice channel pill
    const vcName = (guild.voice_channel && typeof guild.voice_channel === 'object')
      ? guild.voice_channel.name
      : (guild.voice_channel || null);

    if (vcName) {
      if (channelName) channelName.textContent = vcName;
      const count = (guild.listeners && Array.isArray(guild.listeners)) ? guild.listeners.length : 0;
      if (listenerCount) listenerCount.textContent = `${count} listener${count === 1 ? '' : 's'}`;
    } else {
      if (channelName) channelName.textContent = 'Not in Voice';
      if (listenerCount) listenerCount.textContent = '0 listeners';
    }

    // Volume
    const vol = guild.volume !== undefined ? guild.volume : 100;
    if (volumeSlider && document.activeElement !== volumeSlider) {
      volumeSlider.value = vol;
    }
    if (volumeLabel) volumeLabel.textContent = `${vol}%`;

    // Track metadata
    if (track) {
      if (trackTitle) trackTitle.textContent = track.title || 'Unknown Track';
      if (trackArtist) trackArtist.textContent = track.uploader || track.artist || 'SoundCloud Stream';
      if (sourceBadge) sourceBadge.textContent = track.is_url ? 'Direct URL' : 'SoundCloud';

      if (albumArt) {
        albumArt.src = track.thumbnail || '/static/images/vinyl.png';
      }

      currentTrackDuration = track.duration || 0;
      currentTrackStartTime = track.started_at || (Date.now() / 1000 - (track.elapsed || 0));
      if (totalDurationEl) totalDurationEl.textContent = formatDuration(currentTrackDuration);

      if (track.elapsed !== undefined) {
        updateProgress(track.elapsed, currentTrackDuration);
      }
    } else {
      if (trackTitle) trackTitle.textContent = 'No Track Playing';
      if (trackArtist) trackArtist.textContent = 'Queue a track below or use /play in Discord';
      if (sourceBadge) sourceBadge.textContent = 'SoundCloud';
      if (albumArt) albumArt.src = '/static/images/vinyl.png';
      if (currentTimeEl) currentTimeEl.textContent = '0:00';
      if (totalDurationEl) totalDurationEl.textContent = '0:00';
      if (progressBarFill) progressBarFill.style.width = '0%';
      currentTrackDuration = 0;
      currentTrackStartTime = null;
    }

    // Queue
    renderQueue(guild.queue || []);
  }

  function renderNoGuildSelected() {
    isPlaying = false;
    isPaused = false;
    if (statusBadge) statusBadge.textContent = 'NO SERVER';
    if (trackTitle) trackTitle.textContent = 'Select a server to monitor';
    if (trackArtist) trackArtist.textContent = 'No server selected or bot is offline';
    if (channelName) channelName.textContent = 'Not in Voice';
    if (listenerCount) listenerCount.textContent = '0 listeners';
    if (albumArt) albumArt.src = '/static/images/vinyl.png';
    if (artWrap) artWrap.classList.remove('is-playing');
    renderQueue([]);
  }

  function renderQueue(queue) {
    if (!queueCount || !queueList) return;

    queueCount.textContent = queue.length;

    // Remove existing queue items
    const existingItems = queueList.querySelectorAll('.queue-item');
    existingItems.forEach(el => el.remove());

    if (!queue || queue.length === 0) {
      if (queueEmpty) queueEmpty.style.display = 'flex';
      return;
    }

    if (queueEmpty) queueEmpty.style.display = 'none';

    queue.forEach((item, index) => {
      const title = escapeHtml(item.title || 'Unknown Song');
      const artist = escapeHtml(item.uploader || item.artist || 'SoundCloud');
      const duration = formatDuration(item.duration || 0);
      const thumb = escapeHtml(item.thumbnail || '/static/images/vinyl.png');

      const itemDiv = document.createElement('div');
      itemDiv.className = 'queue-item';
      itemDiv.innerHTML = `
        <span class="queue-item-index">${index + 1}</span>
        <img src="${thumb}" alt="Art" class="queue-item-thumb" onerror="this.src='/static/images/vinyl.png'">
        <div class="queue-item-info">
          <span class="queue-item-title" title="${title}">${title}</span>
          <span class="queue-item-artist">${artist} &bull; ${duration}</span>
        </div>
        <button class="btn-remove-track" data-index="${index}" title="Remove track">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      `;

      const removeBtn = itemDiv.querySelector('.btn-remove-track');
      removeBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        removeQueueTrack(index);
      });

      queueList.appendChild(itemDiv);
    });
  }

  function updateVitals(stats) {
    const cpu = stats.cpu_percent !== undefined ? stats.cpu_percent : (stats.cpu || 0);
    const ramMb = stats.ram_used_mb !== undefined ? stats.ram_used_mb : (stats.ram || 0);
    const ping = stats.ping_ms !== undefined ? stats.ping_ms : (stats.ping || 0);
    const streams = stats.total_streams !== undefined ? stats.total_streams : (stats.streams_completed || 0);
    const uptimeStr = stats.uptime_str || formatUptime(stats.uptime_seconds || stats.uptime || 0);
    const guilds = stats.guild_count || 0;

    if (statCpu) statCpu.textContent = `${cpu}%`;
    if (barCpu) barCpu.style.width = `${Math.min(100, Math.max(0, cpu))}%`;

    if (statRam) statRam.textContent = `${ramMb} MB`;
    if (barRam) {
      const ramTotal = stats.ram_total_mb || 512;
      const pct = Math.min(100, (ramMb / ramTotal) * 100);
      barRam.style.width = `${pct}%`;
    }

    if (statUptime) statUptime.textContent = uptimeStr;
    if (statPing) statPing.textContent = `${ping} ms`;
    if (statStreams) statStreams.textContent = streams;
    if (statGuilds) statGuilds.textContent = guilds;
  }

  // --- Smooth Progress Bar Ticker ---
  function updateProgress(elapsedSeconds, totalDuration) {
    if (currentTimeEl) currentTimeEl.textContent = formatDuration(elapsedSeconds);
    if (totalDurationEl) totalDurationEl.textContent = formatDuration(totalDuration);

    if (totalDuration > 0) {
      const pct = Math.min(100, (elapsedSeconds / totalDuration) * 100);
      if (progressBarFill) progressBarFill.style.width = `${pct}%`;
    } else {
      if (progressBarFill) progressBarFill.style.width = '0%';
    }
  }

  function startProgressTicker() {
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(() => {
      if (!isPlaying || isPaused || !currentTrackStartTime) return;
      const now = Date.now() / 1000;
      const elapsed = Math.max(0, now - currentTrackStartTime);
      updateProgress(elapsed, currentTrackDuration);
    }, 500);
  }

  // --- Dynamic Audio Equalizer Simulation ---
  const NUM_BARS = 36;
  const barHeights = new Float32Array(NUM_BARS);
  const targetHeights = new Float32Array(NUM_BARS);

  function resizeEqualizer() {
    if (!equalizerCanvas) return;
    const rect = equalizerCanvas.getBoundingClientRect();
    equalizerCanvas.width = rect.width * (window.devicePixelRatio || 1);
    equalizerCanvas.height = rect.height * (window.devicePixelRatio || 1);
  }

  function animateEqualizer() {
    if (!vCtx || !equalizerCanvas) return;

    requestAnimationFrame(animateEqualizer);

    const w = equalizerCanvas.width;
    const h = equalizerCanvas.height;
    vCtx.clearRect(0, 0, w, h);

    const barWidth = (w / NUM_BARS) - 3;
    const time = Date.now() * 0.0035;

    for (let i = 0; i < NUM_BARS; i++) {
      if (isPlaying && !isPaused) {
        const wave = Math.sin(time * 2.2 + i * 0.28) * 0.45 + 0.5;
        const sub = Math.cos(time * 3.1 - i * 0.18) * 0.35 + 0.35;
        const noise = Math.random() * 0.25;
        const dynamicVal = Math.min(1, Math.max(0.1, (wave * 0.5 + sub * 0.35 + noise) * (0.85 + 0.35 * Math.sin(time + i))));
        targetHeights[i] = dynamicVal * (h * 0.88);
      } else {
        const idleWave = Math.sin(time * 0.8 + i * 0.25) * 0.12 + 0.15;
        targetHeights[i] = idleWave * (h * 0.3);
      }

      barHeights[i] += (targetHeights[i] - barHeights[i]) * 0.25;

      const barHeight = Math.max(4, barHeights[i]);
      const x = i * (barWidth + 3);
      const y = h - barHeight;

      const grad = vCtx.createLinearGradient(0, y, 0, h);
      grad.addColorStop(0, '#00f0ff');
      grad.addColorStop(0.5, '#7928ca');
      grad.addColorStop(1, '#ff0080');

      vCtx.fillStyle = grad;
      vCtx.beginPath();
      vCtx.roundRect(x, y, barWidth, barHeight, [3, 3, 0, 0]);
      vCtx.fill();
    }
  }

  // --- API Client ---
  async function apiCall(endpoint, method = 'POST', body = null) {
    try {
      const opts = {
        method,
        headers: { 'Content-Type': 'application/json' }
      };
      if (body) opts.body = JSON.stringify(body);
      const res = await fetch(endpoint, opts);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || `HTTP error ${res.status}`);
      }
      return data;
    } catch (err) {
      console.error(`API error on ${endpoint}:`, err);
      showToast(err.message || 'Request failed', 'error');
      throw err;
    }
  }

  // --- Control Event Handlers ---
  if (guildSelect) {
    guildSelect.addEventListener('change', function () {
      currentGuildId = this.value;
      const g = allGuilds.find(item => (item.id === currentGuildId || item.guild_id === currentGuildId));
      if (g) renderGuildPlayback(g);
      showToast(`Selected server: ${this.options[this.selectedIndex].text}`, 'info');
    });
  }

  if (btnPlayPause) {
    btnPlayPause.addEventListener('click', async function () {
      if (!currentGuildId) {
        showToast('Please select a server first', 'error');
        return;
      }
      try {
        const res = await apiCall('/api/pause', 'POST', { guild_id: currentGuildId });
        showToast(res.status === 'paused' ? 'Playback Paused' : 'Playback Resumed', 'success');
      } catch (e) {}
    });
  }

  if (btnSkip) {
    btnSkip.addEventListener('click', async function () {
      if (!currentGuildId) return;
      try {
        await apiCall('/api/skip', 'POST', { guild_id: currentGuildId });
        showToast('Skipped track', 'success');
      } catch (e) {}
    });
  }

  if (btnStop) {
    btnStop.addEventListener('click', async function () {
      if (!currentGuildId) return;
      try {
        await apiCall('/api/stop', 'POST', { guild_id: currentGuildId });
        showToast('Stopped playback and left channel', 'info');
      } catch (e) {}
    });
  }

  if (btnPrev) {
    btnPrev.addEventListener('click', function () {
      if (!currentGuildId) return;
      const activeGuild = allGuilds.find(g => (g.id === currentGuildId || g.guild_id === currentGuildId));
      if (activeGuild && activeGuild.current_track && activeGuild.current_track.url) {
        apiCall('/api/play', 'POST', {
          guild_id: currentGuildId,
          query: activeGuild.current_track.url
        });
        showToast('Replaying track', 'info');
      }
    });
  }

  // Volume
  let volumeDebounce = null;
  if (volumeSlider) {
    volumeSlider.addEventListener('input', function () {
      if (volumeLabel) volumeLabel.textContent = `${this.value}%`;
      clearTimeout(volumeDebounce);
      volumeDebounce = setTimeout(() => {
        if (!currentGuildId) return;
        apiCall('/api/volume', 'POST', {
          guild_id: currentGuildId,
          volume: parseInt(this.value, 10)
        });
      }, 150);
    });
  }

  // Search & Enqueue Form
  if (searchForm) {
    searchForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      const query = (searchInput.value || '').trim();
      if (!query) return;

      if (!currentGuildId) {
        showToast('Please select a server first', 'error');
        return;
      }

      btnAddTrack.disabled = true;
      const originalText = btnAddTrack.innerHTML;
      btnAddTrack.innerHTML = '<span>Adding...</span>';

      try {
        const res = await apiCall('/api/play', 'POST', {
          guild_id: currentGuildId,
          query: query
        });
        showToast(`Enqueued: ${res.track ? res.track.title : query}`, 'success');
        searchInput.value = '';
      } catch (err) {
        // Handled in apiCall
      } finally {
        btnAddTrack.disabled = false;
        btnAddTrack.innerHTML = originalText;
      }
    });
  }

  async function removeQueueTrack(index) {
    if (!currentGuildId) return;
    try {
      await apiCall('/api/queue/remove', 'POST', {
        guild_id: currentGuildId,
        index: index
      });
      showToast(`Removed track #${index + 1}`, 'info');
    } catch (e) {}
  }

  // --- Sleek Toast Notifications ---
  function showToast(message, type = 'info') {
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = 'toast';

    let iconSvg = 'ℹ️';
    if (type === 'success') iconSvg = '✅';
    if (type === 'error') iconSvg = '⚠️';

    toast.innerHTML = `<span>${iconSvg}</span> <span>${escapeHtml(message)}</span>`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // --- Utilities ---
  function formatDuration(seconds) {
    if (isNaN(seconds) || seconds <= 0) return '0:00';
    const s = Math.floor(seconds);
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    const hours = Math.floor(mins / 60);

    if (hours > 0) {
      const remMins = mins % 60;
      return `${hours}:${remMins < 10 ? '0' : ''}${remMins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  }

  function formatUptime(seconds) {
    if (isNaN(seconds) || seconds <= 0) return '00:00:00';
    const s = Math.floor(seconds);
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;

    if (d > 0) return `${d}d ${h}h ${m}m`;
    return `${h < 10 ? '0' : ''}${h}:${m < 10 ? '0' : ''}${m}:${sec < 10 ? '0' : ''}${sec}`;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --- Boot ---
  window.addEventListener('DOMContentLoaded', () => {
    resizeEqualizer();
    window.addEventListener('resize', resizeEqualizer);
    animateEqualizer();
    startProgressTicker();
    connectWebSocket();
  });

})();
