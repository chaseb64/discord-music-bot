/**
 * Aether Beats - Discord Music Command Center
 * Real-time WebSocket Client, Interactive Scrubber, DSP Audio FX,
 * Synchronized Karaoke Lyrics, Smart Queue Engine & MP3 File Upload
 */

(function () {
  'use strict';

  // --- State Variables ---
  let currentGuildId = null;
  let allGuilds = [];
  let currentTrackStartTime = null;
  let currentTrackDuration = 0;
  let currentTrackTitle = '';
  let isPlaying = false;
  let isPaused = false;
  const NUM_BARS = 36;
  const realAudioBands = new Float32Array(NUM_BARS);
  let lastAudioBandTime = 0;
  let ws = null;
  let reconnectTimeout = null;
  let progressInterval = null;
  let currentLyrics = null;
  let currentLoopMode = 'off';
  let isAutoplayEnabled = false;

  // --- DOM Elements ---
  const guildSelect = document.getElementById('guildSelect');
  const wsStatus = document.getElementById('wsStatus');

  const albumArtWrap = document.getElementById('albumArtWrap');
  const albumArt = document.getElementById('albumArt');
  const statusBadge = document.getElementById('statusBadge');
  const sourceBadge = document.getElementById('sourceBadge');
  const activeFilterBadge = document.getElementById('activeFilterBadge');
  const trackTitle = document.getElementById('trackTitle');
  const trackArtist = document.getElementById('trackArtist');

  const equalizerCanvas = document.getElementById('equalizerCanvas');
  const vCtx = equalizerCanvas ? equalizerCanvas.getContext('2d') : null;

  // Scrubber Elements
  const progressBarWrap = document.getElementById('progressBarWrap');
  const progressBarFill = document.getElementById('progressBarFill');
  const progressHandle = document.getElementById('progressHandle');
  const progressTooltip = document.getElementById('progressTooltip');
  const currentTimeEl = document.getElementById('currentTime');
  const totalDurationEl = document.getElementById('totalDuration');

  // Playback Control Buttons
  const btnPrev = document.getElementById('btnPrev');
  const btnPlayPause = document.getElementById('btnPlayPause');
  const playPauseIcon = document.getElementById('playPauseIcon');
  const btnSkip = document.getElementById('btnSkip');
  const btnStop = document.getElementById('btnStop');
  const btnLoop = document.getElementById('btnLoop');
  const loopChip = document.getElementById('loopChip');
  const btnShuffle = document.getElementById('btnShuffle');
  const btnLyricsToggle = document.getElementById('btnLyricsToggle');

  // Volume
  const volumeSlider = document.getElementById('volumeSlider');
  const volumeLabel = document.getElementById('volumeLabel');
  const volIcon = document.getElementById('volIcon');

  // DSP FX Elements
  const activeFilterLabel = document.getElementById('activeFilterLabel');
  const fxButtonGroup = document.getElementById('fxButtonGroup');

  // Lyrics Elements
  const lyricsCard = document.getElementById('lyricsCard');
  const lyricsCardTitle = document.getElementById('lyricsCardTitle');
  const lyricsContainer = document.getElementById('lyricsContainer');
  const lyricsSyncBadge = document.getElementById('lyricsSyncBadge');
  const btnCloseLyrics = document.getElementById('btnCloseLyrics');

  // Search & MP3 File Upload Form
  const searchForm = document.getElementById('searchForm');
  const searchInput = document.getElementById('searchInput');
  const btnAddTrack = document.getElementById('btnAddTrack');
  const mp3UploadInput = document.getElementById('mp3UploadInput');
  const btnUploadLabel = document.getElementById('btnUploadLabel');
  const uploadLabelText = document.getElementById('uploadLabelText');
  const uploadDropzone = document.getElementById('uploadDropzone');

  // Queue Elements
  const queueList = document.getElementById('queueList');
  const queueEmpty = document.getElementById('queueEmpty');
  const queueCount = document.getElementById('queueCount');
  const btnAutoplayToggle = document.getElementById('btnAutoplayToggle');
  const btnShuffleQueue = document.getElementById('btnShuffleQueue');

  // System Vitals Elements
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
      setConnectionStatus('online', 'LIVE SYNC');
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }
    };

    ws.onmessage = function (event) {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'visualizer_update' && message.bands_by_guild) {
          const bands = message.bands_by_guild[currentGuildId];
          if (bands && Array.isArray(bands)) {
            for (let i = 0; i < Math.min(NUM_BARS, bands.length); i++) {
              realAudioBands[i] = bands[i];
            }
            lastAudioBandTime = Date.now();
          }
          return;
        }

        if (message.type === 'initial_state' || message.type === 'state_update') {
          handleStateUpdate(message);
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
    if (wsStatus) {
      const dot = wsStatus.querySelector('.pulse-dot');
      const label = wsStatus.querySelector('.status-label');
      if (label) label.textContent = text;
      if (dot) {
        dot.style.background = status === 'online' ? '#10B981' : (status === 'connecting' ? '#F59E0B' : '#F43F5E');
        dot.style.boxShadow = status === 'online' ? '0 0 10px #10B981' : 'none';
      }
    }
  }

  // --- State Handler ---
  function handleStateUpdate(data) {
    if (data.metrics) {
      updateVitals(data.metrics);
    }

    if (data.guilds && Array.isArray(data.guilds)) {
      allGuilds = data.guilds;
      populateGuildSelector(allGuilds);

      // Default to first active or first guild if none selected
      if (!currentGuildId && allGuilds.length > 0) {
        const activeGuild = allGuilds.find(g => g.is_playing) || allGuilds[0];
        currentGuildId = activeGuild.id || activeGuild.guild_id;
        if (guildSelect) guildSelect.value = currentGuildId;
      }

      if (currentGuildId) {
        const guild = allGuilds.find(g => (g.id === currentGuildId || g.guild_id === currentGuildId));
        if (guild) {
          renderGuildPlayback(guild);
        } else {
          renderNoGuildSelected();
        }
      }
    }
  }

  function populateGuildSelector(guilds) {
    if (!guildSelect) return;
    const currentVal = guildSelect.value;
    guildSelect.innerHTML = '';

    if (guilds.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No Servers Available';
      guildSelect.appendChild(opt);
      return;
    }

    guilds.forEach(g => {
      const opt = document.createElement('option');
      opt.value = g.id || g.guild_id;
      const playingBadge = g.is_playing ? ' 🔊 [PLAYING]' : '';
      opt.textContent = `${g.name || g.guild_name || 'Discord Server'}${playingBadge}`;
      guildSelect.appendChild(opt);
    });

    if (currentVal && guilds.some(g => (g.id === currentVal || g.guild_id === currentVal))) {
      guildSelect.value = currentVal;
    } else if (guilds.length > 0) {
      guildSelect.value = guilds[0].id || guilds[0].guild_id;
    }
  }

  function renderGuildPlayback(guild) {
    isPlaying = !!guild.is_playing;
    isPaused = !!guild.is_paused;

    // Channel & Listener info
    if (guild.voice_channel && guild.voice_channel.name) {
      if (channelName) channelName.textContent = guild.voice_channel.name;
      const count = (guild.listeners && Array.isArray(guild.listeners)) ? guild.listeners.length : 0;
      if (listenerCount) listenerCount.textContent = `${count} listener${count === 1 ? '' : 's'}`;
    } else {
      if (channelName) channelName.textContent = 'Not in Voice';
      if (listenerCount) listenerCount.textContent = '0 listeners';
    }

    // Play/Pause button state
    if (playPauseIcon) {
      playPauseIcon.innerHTML = isPlaying ? ICON_PAUSE : ICON_PLAY;
    }

    // Status Badge
    if (statusBadge) {
      if (isPlaying) {
        statusBadge.textContent = 'PLAYING';
        statusBadge.style.background = 'rgba(16, 185, 129, 0.15)';
        statusBadge.style.color = '#34D399';
        statusBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        if (albumArtWrap) albumArtWrap.classList.add('is-playing');
      } else if (isPaused) {
        statusBadge.textContent = 'PAUSED';
        statusBadge.style.background = 'rgba(245, 158, 11, 0.15)';
        statusBadge.style.color = '#FBBF24';
        statusBadge.style.borderColor = 'rgba(245, 158, 11, 0.3)';
        if (albumArtWrap) albumArtWrap.classList.remove('is-playing');
      } else {
        statusBadge.textContent = 'IDLE';
        statusBadge.style.background = 'rgba(88, 101, 242, 0.15)';
        statusBadge.style.color = '#A5B4FC';
        statusBadge.style.borderColor = 'rgba(88, 101, 242, 0.3)';
        if (albumArtWrap) albumArtWrap.classList.remove('is-playing');
      }
    }

    // Track metadata
    const track = guild.current_track;
    if (track) {
      const prevTitle = currentTrackTitle;
      currentTrackTitle = track.title || 'Unknown Track';
      if (trackTitle) trackTitle.textContent = currentTrackTitle;
      if (trackArtist) trackArtist.textContent = track.uploader || track.artist || 'SoundCloud Stream';
      if (sourceBadge) {
        sourceBadge.textContent = track.is_local ? 'Local Upload' : (track.is_url ? 'Direct URL' : 'SoundCloud');
      }

      if (albumArt) {
        albumArt.src = track.thumbnail || '/static/images/vinyl.png';
      }

      currentTrackDuration = track.duration || 0;
      currentTrackStartTime = track.started_at || (Date.now() / 1000 - (track.elapsed || 0));
      if (totalDurationEl) totalDurationEl.textContent = formatDuration(currentTrackDuration);

      if (track.elapsed !== undefined) {
        updateProgress(track.elapsed, currentTrackDuration);
      }

      // Automatically fetch lyrics if song changed and lyrics drawer is open
      if (prevTitle !== currentTrackTitle && lyricsCard && lyricsCard.style.display !== 'none') {
        loadLyrics(currentTrackTitle, track.artist);
      }
    } else {
      currentTrackTitle = '';
      if (trackTitle) trackTitle.textContent = 'No Track Playing';
      if (trackArtist) trackArtist.textContent = 'Queue a track below, upload an MP3, or use /play in Discord';
      if (sourceBadge) sourceBadge.textContent = 'SoundCloud';
      if (albumArt) albumArt.src = '/static/images/vinyl.png';
      if (currentTimeEl) currentTimeEl.textContent = '0:00';
      if (totalDurationEl) totalDurationEl.textContent = '0:00';
      if (progressBarFill) progressBarFill.style.width = '0%';
      currentTrackDuration = 0;
      currentTrackStartTime = null;
    }

    // Volume
    const vol = guild.volume !== undefined ? guild.volume : 100;
    if (volumeSlider && document.activeElement !== volumeSlider) {
      volumeSlider.value = vol;
    }
    if (volumeLabel) volumeLabel.textContent = `${vol}%`;

    // Active Filter
    const activeFilter = guild.active_filter || 'none';
    updateActiveFilterUI(activeFilter);

    // Loop Mode
    currentLoopMode = guild.loop_mode || 'off';
    updateLoopUI(currentLoopMode);

    // Autoplay
    isAutoplayEnabled = !!guild.autoplay;
    updateAutoplayUI(isAutoplayEnabled);

    // Initial audio bands
    if (guild.visualizer_bands && Array.isArray(guild.visualizer_bands)) {
      for (let i = 0; i < Math.min(NUM_BARS, guild.visualizer_bands.length); i++) {
        realAudioBands[i] = guild.visualizer_bands[i];
      }
      lastAudioBandTime = Date.now();
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
    if (albumArtWrap) albumArtWrap.classList.remove('is-playing');
    renderQueue([]);
  }

  function updateActiveFilterUI(filterName) {
    if (activeFilterLabel) {
      const names = {
        'none': 'Normal',
        'bassboost': 'Bass Boost',
        'nightcore': 'Nightcore',
        'vaporwave': 'Vaporwave',
        '8d': '8D Audio',
        'treble': 'Treble'
      };
      activeFilterLabel.textContent = names[filterName] || filterName;
    }

    if (activeFilterBadge) {
      if (filterName && filterName !== 'none') {
        activeFilterBadge.style.display = 'inline-flex';
        activeFilterBadge.textContent = `FX: ${filterName.toUpperCase()}`;
      } else {
        activeFilterBadge.style.display = 'none';
      }
    }

    document.querySelectorAll('.btn-fx').forEach(btn => {
      if (btn.dataset.filter === filterName) {
        btn.classList.add('is-active');
      } else {
        btn.classList.remove('is-active');
      }
    });
  }

  function updateLoopUI(mode) {
    if (loopChip) {
      loopChip.textContent = mode.toUpperCase();
      if (mode === 'off') {
        loopChip.style.background = 'rgba(255, 255, 255, 0.15)';
        if (btnLoop) btnLoop.classList.remove('is-active');
      } else if (mode === 'track') {
        loopChip.style.background = 'var(--cyan)';
        if (btnLoop) btnLoop.classList.add('is-active');
      } else if (mode === 'queue') {
        loopChip.style.background = 'var(--purple)';
        if (btnLoop) btnLoop.classList.add('is-active');
      }
    }
  }

  function updateAutoplayUI(enabled) {
    if (btnAutoplayToggle) {
      if (enabled) {
        btnAutoplayToggle.classList.add('is-active');
      } else {
        btnAutoplayToggle.classList.remove('is-active');
      }
    }
  }

  function renderQueue(queue) {
    if (!queueCount || !queueList) return;
    queueCount.textContent = queue.length;

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
        <div class="queue-item-actions">
          ${index > 0 ? `<button class="btn-queue-move btn-move-up" data-idx="${index}" title="Move Up"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg></button>` : ''}
          ${index < queue.length - 1 ? `<button class="btn-queue-move btn-move-down" data-idx="${index}" title="Move Down"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg></button>` : ''}
          <button class="btn-remove-track" data-index="${index}" title="Remove track">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="18" x2="18" y2="18"></line></svg>
          </button>
        </div>
      `;

      // Event handlers for queue items
      const btnUp = itemDiv.querySelector('.btn-move-up');
      if (btnUp) {
        btnUp.addEventListener('click', (e) => {
          e.stopPropagation();
          reorderQueueTrack(index, index - 1);
        });
      }

      const btnDown = itemDiv.querySelector('.btn-move-down');
      if (btnDown) {
        btnDown.addEventListener('click', (e) => {
          e.stopPropagation();
          reorderQueueTrack(index, index + 1);
        });
      }

      const removeBtn = itemDiv.querySelector('.btn-remove-track');
      if (removeBtn) {
        removeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          removeQueueTrack(index);
        });
      }

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

  // --- Smooth Progress Bar & Scrubber Ticker ---
  function updateProgress(elapsedSeconds, totalDuration) {
    if (currentTimeEl) currentTimeEl.textContent = formatDuration(elapsedSeconds);
    if (totalDurationEl) totalDurationEl.textContent = formatDuration(totalDuration);

    if (totalDuration > 0) {
      const pct = Math.min(100, Math.max(0, (elapsedSeconds / totalDuration) * 100));
      if (progressBarFill) progressBarFill.style.width = `${pct}%`;
      if (progressHandle) progressHandle.style.left = `${pct}%`;
    } else {
      if (progressBarFill) progressBarFill.style.width = '0%';
      if (progressHandle) progressHandle.style.left = '0%';
    }

    // Real-time Karaoke line highlighter
    syncKaraokeLine(elapsedSeconds);
  }

  function startProgressTicker() {
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(() => {
      if (!isPlaying || isPaused || !currentTrackStartTime) return;
      const now = Date.now() / 1000;
      const elapsed = Math.max(0, now - currentTrackStartTime);
      updateProgress(elapsed, currentTrackDuration);
    }, 400);
  }

  // --- Interactive Scrubber Seek Listener ---
  if (progressBarWrap) {
    progressBarWrap.addEventListener('mousemove', function (e) {
      if (!currentTrackDuration || currentTrackDuration <= 0) return;
      const rect = this.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const hoverSecs = pct * currentTrackDuration;

      if (progressTooltip) {
        progressTooltip.textContent = formatDuration(hoverSecs);
        progressTooltip.style.left = `${pct * 100}%`;
      }
    });

    progressBarWrap.addEventListener('click', async function (e) {
      if (!currentGuildId || !currentTrackDuration || currentTrackDuration <= 0) return;
      const rect = this.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const targetSec = pct * currentTrackDuration;

      updateProgress(targetSec, currentTrackDuration);
      try {
        await apiCall('/api/seek', 'POST', {
          guild_id: currentGuildId,
          position: targetSec
        });
        showToast(`Seeked to ${formatDuration(targetSec)}`, 'info');
      } catch (err) {}
    });
  }

  // --- Dynamic Audio Equalizer (Real-Time Music FFT) ---
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
    const time = Date.now() * 0.003;
    const hasLiveAudio = (isPlaying && !isPaused && (Date.now() - lastAudioBandTime < 800));

    for (let i = 0; i < NUM_BARS; i++) {
      if (hasLiveAudio) {
        const bandVal = realAudioBands[i] || 0.0;
        targetHeights[i] = Math.max(3, bandVal * (h * 0.90));
      } else if (isPlaying && !isPaused) {
        const idleWave = Math.sin(time * 2.0 + i * 0.25) * 0.15 + 0.2;
        targetHeights[i] = idleWave * (h * 0.4);
      } else {
        const idleWave = Math.sin(time * 0.7 + i * 0.2) * 0.04 + 0.05;
        targetHeights[i] = idleWave * (h * 0.2);
      }

      // Responsive attack (0.75) and smooth natural decay (0.22)
      const diff = targetHeights[i] - barHeights[i];
      if (diff > 0) {
        barHeights[i] += diff * 0.75;
      } else {
        barHeights[i] += diff * 0.22;
      }

      const barHeight = Math.max(3, barHeights[i]);
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

  // --- Synchronized Karaoke Lyrics Engine ---
  async function loadLyrics(title, artist) {
    if (!lyricsContainer) return;
    lyricsContainer.innerHTML = '<div class="lyrics-loading">Fetching synchronized lyrics from LRCLIB...</div>';

    if (lyricsCardTitle) lyricsCardTitle.textContent = `Lyrics: ${title || 'Current Track'}`;
    if (lyricsSyncBadge) {
      lyricsSyncBadge.textContent = 'FETCHING';
      lyricsSyncBadge.style.color = '#F59E0B';
      lyricsSyncBadge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
    }

    try {
      const q = new URLSearchParams({ guild_id: currentGuildId || '' });
      if (title) q.append('title', title);
      if (artist) q.append('artist', artist);

      const res = await fetch(`/api/lyrics?${q.toString()}`);
      const data = await res.json();
      if (!res.ok || !data.lyrics) throw new Error(data.error || 'No lyrics found');

      currentLyrics = data.lyrics;
      renderLyrics(currentLyrics);
    } catch (err) {
      lyricsContainer.innerHTML = `<div class="lyrics-plain">No lyrics found for "${escapeHtml(title)}".</div>`;
      if (lyricsSyncBadge) {
        lyricsSyncBadge.textContent = 'NO LYRICS';
        lyricsSyncBadge.style.color = '#64748B';
        lyricsSyncBadge.style.borderColor = 'rgba(255, 255, 255, 0.1)';
      }
    }
  }

  function renderLyrics(lyrics) {
    if (!lyricsContainer) return;
    lyricsContainer.innerHTML = '';

    if (lyrics.has_synced && lyrics.synced_lines && lyrics.synced_lines.length > 0) {
      if (lyricsSyncBadge) {
        lyricsSyncBadge.textContent = 'SYNCED KARAOKE';
        lyricsSyncBadge.style.color = '#10B981';
        lyricsSyncBadge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
      }

      lyrics.synced_lines.forEach((line, idx) => {
        const lineEl = document.createElement('div');
        lineEl.className = 'lyric-line';
        lineEl.dataset.time = line.time;
        lineEl.dataset.index = idx;
        lineEl.textContent = line.text;

        // Click lyric line to jump directly to that timestamp in song!
        lineEl.addEventListener('click', function () {
          if (!currentGuildId) return;
          const seekTime = parseFloat(this.dataset.time);
          apiCall('/api/seek', 'POST', { guild_id: currentGuildId, position: seekTime });
          updateProgress(seekTime, currentTrackDuration);
          showToast(`Jumped to ${formatDuration(seekTime)}`, 'info');
        });

        lyricsContainer.appendChild(lineEl);
      });
    } else {
      if (lyricsSyncBadge) {
        lyricsSyncBadge.textContent = 'PLAIN TEXT';
        lyricsSyncBadge.style.color = '#A5B4FC';
        lyricsSyncBadge.style.borderColor = 'rgba(88, 101, 242, 0.4)';
      }
      const plainDiv = document.createElement('div');
      plainDiv.className = 'lyrics-plain';
      plainDiv.textContent = lyrics.plain_text || 'No lyrics text available.';
      lyricsContainer.appendChild(plainDiv);
    }
  }

  function syncKaraokeLine(elapsedSeconds) {
    if (!lyricsContainer || !currentLyrics || !currentLyrics.has_synced) return;
    const lines = lyricsContainer.querySelectorAll('.lyric-line');
    if (!lines || lines.length === 0) return;

    let activeLine = null;
    lines.forEach((lineEl, idx) => {
      const time = parseFloat(lineEl.dataset.time);
      const nextTime = idx < lines.length - 1 ? parseFloat(lines[idx + 1].dataset.time) : Infinity;

      if (elapsedSeconds >= time && elapsedSeconds < nextTime) {
        lineEl.classList.add('is-active');
        activeLine = lineEl;
      } else {
        lineEl.classList.remove('is-active');
      }
    });

    if (activeLine) {
      activeLine.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  // --- Custom MP3 / Audio File Upload ---
  async function uploadAudioFile(file) {
    if (!file || !currentGuildId) {
      showToast('Please select a server first', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('guild_id', currentGuildId);
    formData.append('file', file);

    showToast(`Uploading ${file.name}...`, 'info');
    if (uploadLabelText) uploadLabelText.textContent = 'Uploading...';

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Upload failed');
      showToast(`Added MP3: ${data.track ? data.track.title : file.name}`, 'success');
    } catch (err) {
      showToast(err.message || 'Failed to upload audio file', 'error');
    } finally {
      if (uploadLabelText) uploadLabelText.textContent = 'Upload MP3';
    }
  }

  // --- Control Event Handlers ---
  if (guildSelect) {
    guildSelect.addEventListener('change', function () {
      currentGuildId = this.value;
      const g = allGuilds.find(item => (item.id === currentGuildId || item.guild_id === currentGuildId));
      if (g) renderGuildPlayback(g);
      showToast(`Selected server: ${this.options[this.selectedIndex].text}`, 'info');
      if (lyricsCard && lyricsCard.style.display !== 'none' && currentTrackTitle) {
        loadLyrics(currentTrackTitle, '');
      }
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
        btnStop.disabled = true;
        const res = await apiCall('/api/stop', 'POST', { guild_id: currentGuildId });
        showToast(res.message || 'Stopped playback and left channel', 'info');
        isPlaying = false;
        isPaused = false;
        realAudioBands.fill(0);
        targetHeights.fill(0);
        if (channelName) channelName.textContent = 'Not in Voice';
        if (listenerCount) listenerCount.textContent = '0 listeners';
        if (statusBadge) {
          statusBadge.textContent = 'IDLE';
          statusBadge.style.background = 'rgba(88, 101, 242, 0.15)';
          statusBadge.style.color = '#A5B4FC';
          statusBadge.style.borderColor = 'rgba(88, 101, 242, 0.3)';
        }
        if (albumArtWrap) albumArtWrap.classList.remove('is-playing');
        if (playPauseIcon) playPauseIcon.innerHTML = ICON_PLAY;
        if (trackTitle) trackTitle.textContent = 'No Track Playing';
        if (trackArtist) trackArtist.textContent = 'Queue a track below, upload an MP3, or use /play in Discord';
        if (currentTimeEl) currentTimeEl.textContent = '0:00';
        if (totalDurationEl) totalDurationEl.textContent = '0:00';
        if (progressBarFill) progressBarFill.style.width = '0%';
        renderQueue([]);
      } catch (e) {
      } finally {
        btnStop.disabled = false;
      }
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

  // Loop Mode Switcher
  if (btnLoop) {
    btnLoop.addEventListener('click', async function () {
      if (!currentGuildId) return;
      const modes = ['off', 'track', 'queue'];
      const nextIdx = (modes.indexOf(currentLoopMode) + 1) % modes.length;
      const nextMode = modes[nextIdx];
      try {
        const res = await apiCall('/api/loop', 'POST', { guild_id: currentGuildId, mode: nextMode });
        currentLoopMode = nextMode;
        updateLoopUI(nextMode);
        showToast(res.message || `Loop: ${nextMode.toUpperCase()}`, 'info');
      } catch (e) {}
    });
  }

  // Shuffle Queue
  function handleShuffle() {
    if (!currentGuildId) return;
    apiCall('/api/shuffle', 'POST', { guild_id: currentGuildId })
      .then(res => showToast(res.message || 'Queue shuffled!', 'success'))
      .catch(() => {});
  }
  if (btnShuffle) btnShuffle.addEventListener('click', handleShuffle);
  if (btnShuffleQueue) btnShuffleQueue.addEventListener('click', handleShuffle);

  // Autoplay Toggle
  if (btnAutoplayToggle) {
    btnAutoplayToggle.addEventListener('click', async function () {
      if (!currentGuildId) return;
      try {
        const res = await apiCall('/api/autoplay', 'POST', { guild_id: currentGuildId });
        isAutoplayEnabled = !!res.autoplay;
        updateAutoplayUI(isAutoplayEnabled);
        showToast(res.message || `Autoplay ${isAutoplayEnabled ? 'Enabled' : 'Disabled'}`, 'info');
      } catch (e) {}
    });
  }

  // Karaoke Lyrics Toggle
  if (btnLyricsToggle) {
    btnLyricsToggle.addEventListener('click', function () {
      if (!lyricsCard) return;
      const isOpen = lyricsCard.style.display !== 'none';
      if (isOpen) {
        lyricsCard.style.display = 'none';
        btnLyricsToggle.classList.remove('is-active');
      } else {
        lyricsCard.style.display = 'block';
        btnLyricsToggle.classList.add('is-active');
        if (currentTrackTitle) {
          loadLyrics(currentTrackTitle, '');
        }
      }
    });
  }

  if (btnCloseLyrics) {
    btnCloseLyrics.addEventListener('click', function () {
      if (lyricsCard) lyricsCard.style.display = 'none';
      if (btnLyricsToggle) btnLyricsToggle.classList.remove('is-active');
    });
  }

  // DSP FX Button Group Handlers
  document.querySelectorAll('.btn-fx').forEach(btn => {
    btn.addEventListener('click', async function () {
      if (!currentGuildId) {
        showToast('Please select a server first', 'error');
        return;
      }
      const filter = this.dataset.filter;
      try {
        const res = await apiCall('/api/filter', 'POST', { guild_id: currentGuildId, filter });
        showToast(res.message || `Filter set to ${filter}`, 'success');
        updateActiveFilterUI(filter);
      } catch (e) {}
    });
  });

  // MP3 Upload File Input Handler
  if (mp3UploadInput) {
    mp3UploadInput.addEventListener('change', async function () {
      if (!this.files || this.files.length === 0) return;
      const file = this.files[0];
      await uploadAudioFile(file);
      this.value = '';
    });
  }

  // Drag & Drop Zone Handlers
  if (uploadDropzone) {
    uploadDropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadDropzone.classList.add('is-dragover');
    });
    uploadDropzone.addEventListener('dragleave', () => {
      uploadDropzone.classList.remove('is-dragover');
    });
    uploadDropzone.addEventListener('drop', async (e) => {
      e.preventDefault();
      uploadDropzone.classList.remove('is-dragover');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const file = e.dataTransfer.files[0];
        await uploadAudioFile(file);
      }
    });
    uploadDropzone.addEventListener('click', () => {
      if (mp3UploadInput) mp3UploadInput.click();
    });
  }

  // Volume Slider
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

  async function reorderQueueTrack(fromIdx, toIdx) {
    if (!currentGuildId) return;
    try {
      await apiCall('/api/queue/move', 'POST', {
        guild_id: currentGuildId,
        from_index: fromIdx,
        to_index: toIdx
      });
    } catch (e) {}
  }

  // --- Sleek Toast Notifications ---
  function showToast(message, type = 'info') {
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let iconSvg = 'ℹ️';
    if (type === 'success') iconSvg = '✅';
    if (type === 'error') iconSvg = '⚠️';

    toast.innerHTML = `<span class="toast-icon">${iconSvg}</span> <span>${escapeHtml(message)}</span>`;
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
    if (isNaN(seconds) || seconds <= 0) return '0m 0s';
    const s = Math.floor(seconds);
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;

    if (d > 0) return `${d}d ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m ${sec}s`;
    return `${m}m ${sec}s`;
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
