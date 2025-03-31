// --- Base DOM Elements ---
const mapFrame = document.getElementById('mapFrame');
const timestampElement = document.getElementById('timestamp');
const playerCountElement = document.getElementById('playerCount');
const buttons = document.querySelectorAll('.map-button');
const markerForm = document.getElementById('markerForm');
const markerButton = document.getElementById('marker');
const markerXInput = document.getElementById('markerX');
const markerZInput = document.getElementById('markerZ');
const markerTextInput = document.getElementById('markerText');
const addMarkerButton = document.getElementById('addMarkerButton');
const reloadButton = document.getElementById('reloadButton');
const mobileHeaderToggle = document.getElementById('mobileHeaderToggle');
const headerSecondary = document.getElementById('headerSecondary');

/* ==========================================================================
   Initialization on DOM Ready
   ========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  // --- Mobile Header Toggle ---
  // Toggles visibility of the secondary header section on mobile viewports.
  if (mobileHeaderToggle && headerSecondary) {
    mobileHeaderToggle.addEventListener('click', () => {
      headerSecondary.classList.toggle('visible');
    });
  } else {
    if (!mobileHeaderToggle) console.warn('Mobile header toggle element (#mobileHeaderToggle) not found.');
    if (!headerSecondary) console.warn('Secondary header element (#headerSecondary) not found.');
  }

  // --- Coordinate Handling via Iframe Communication ---
  setupCoordinateListener();
  // --- Player Count Update ---
  setupPlayerCountUpdater();
  // --- Map Tab Button Logic ---
  setupMapTabs();
  // --- Map Update (Reload) Button ---
  setupReloadButton();
  // --- Marker Panel Toggle ---
  setupMarkerPanelToggle();
  // --- Add Marker Button ---
  setupAddMarkerButton();
  // --- Initial State ---
  const initialMap = document.querySelector('.map-button.active')?.getAttribute('data-map') || 'world';
  updateTimestamp(initialMap); // Load timestamp for the default map
  // Fade-in body content after load
  document.body.classList.add('content-visible');
}); // End DOMContentLoaded

/* ==========================================================================
   Helper Functions & Event Listener Setups
   ========================================================================== */

/**
 * Listens for keyboard events (Ctrl+C) and messages from the map iframe
 * to fetch and populate coordinates in the marker form.
 */
function setupCoordinateListener() {
  if (!mapFrame) return;

  // Listen for Ctrl+C outside of inputs to request coordinates
  window.addEventListener('keydown', (event) => {
    const isInputElement = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement;
    if (document.activeElement !== mapFrame && !isInputElement) {
      if (event.ctrlKey && (event.key === 'c' || event.key === 'C')) {
        event.preventDefault();
        try {
          const targetOrigin = window.location.origin; // Assume same-origin iframe
          mapFrame.contentWindow.postMessage({ type: 'requestCoordinates' }, targetOrigin);
        } catch (e) {
          console.error('Error posting message to iframe:', e);
        }
      }
    }
  });

  // Listen for coordinate messages back from the iframe
  window.addEventListener('message', (event) => {
    if (event.source === mapFrame.contentWindow && event.origin === window.location.origin) {
      const { data } = event;
      if (data && data.type === 'coordinates') {
        if (markerXInput) markerXInput.value = data.coords.x ?? '';
        if (markerZInput) markerZInput.value = data.coords.z ?? '';
      }
    }
  });
}

/**
 * Sets up fetching and displaying the current player count.
 */
function setupPlayerCountUpdater() {
  if (!playerCountElement) return;

  const update = () => {
    fetch('/get_player_count')
      .then((response) => (response.ok ? response.json() : Promise.reject(`HTTP ${response.status}`)))
      .then((data) => {
        if (data.error) {
          playerCountElement.textContent = 'Server offline';
          playerCountElement.style.color = '#FF8080';
        } else if (data.online !== undefined) {
          const count = data.online;
          playerCountElement.textContent = `${count} Player${count !== 1 ? 's' : ''} online`;
          playerCountElement.style.color = ''; // Reset color
        } else {
          playerCountElement.textContent = 'Invalid Data';
          playerCountElement.style.color = '#FFCC00';
        }
      })
      .catch((error) => {
        console.error('Player count fetch error:', error);
        playerCountElement.textContent = 'Server offline';
        playerCountElement.style.color = '#FF8080';
      });
  };

  update(); // Initial fetch
  // setInterval(update, 30000); // Optional: Periodic refresh
}

/**
 * Handles API errors by logging and showing an alert.
 * @param {Error} error - The error object.
 * @param {string} action - Description of the action that failed (e.g., 'update map').
 */
function handleApiError(error, action) {
  console.error(`${action} error:`, error);
  let message = `Failed to ${action}. Please try again later.`;
  if (error && error.message) {
    if (error.message.includes('password') || error.message.includes('Unauthorized') || error.message.includes('401')) {
      message = 'Incorrect password.';
    } else if (error.message.startsWith('HTTP')) {
      message = `Failed to ${action}. Server error: ${error.message}`;
    } else {
      message = error.message; // Use server-provided error if available
    }
  }
  alert(message);
}

/**
 * Fetches and displays the last updated timestamp for a given map.
 * @param {string} map - The map identifier (e.g., 'world', 'nether').
 */
function updateTimestamp(map) {
  if (!timestampElement) return;
  timestampElement.textContent = `Map updated: Loading...`;

  fetch(`/get_file_date?map=${map}`)
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
    .then((data) => {
      timestampElement.textContent = data.last_updated ? `Map updated: ${data.last_updated}` : `Map updated: Date unavailable`;
    })
    .catch((err) => {
      console.error('Timestamp fetch error:', err);
      timestampElement.textContent = `Map updated: Error loading`;
    });
}

/**
 * Sets up event listeners for the map selection tabs.
 */
function setupMapTabs() {
  if (!mapFrame || buttons.length === 0) return;

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      // Update active state
      buttons.forEach((btn) => btn.classList.remove('active'));
      button.classList.add('active');

      // Change map source and update timestamp
      const map = button.getAttribute('data-map');
      mapFrame.src = `/maps/${map}/index.html`;
      updateTimestamp(map);
    });
  });
}

/**
 * Sets up the event listener for the "Update Map" (reload) button.
 * Requires password prompt and handles API interaction.
 */
function setupReloadButton() {
  if (!reloadButton) return;

  reloadButton.addEventListener('click', () => {
    const activeMap = document.querySelector('.map-button.active')?.getAttribute('data-map') || 'world';
    const userSecret = prompt('Password to update map:');

    if (userSecret === null) return; // Cancelled
    if (!userSecret) {
      alert('Password cannot be empty.');
      return;
    }

    reloadButton.disabled = true;
    reloadButton.textContent = 'Updating...';

    fetch('/update_map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Action-Secret': userSecret },
      body: JSON.stringify({ map: activeMap }),
    })
      .then((response) => {
        if (response.status === 401) throw new Error('Incorrect password.');
        if (!response.ok) {
          return response
            .json()
            .then((err) => Promise.reject(new Error(err.error || `HTTP ${response.status}`)))
            .catch(() => Promise.reject(new Error(`HTTP ${response.status}`)));
        }
        return response.json();
      })
      .then((data) => {
        alert(data.message || 'Map update started.');
        updateTimestamp(activeMap);
        if (mapFrame) mapFrame.src = `/maps/${activeMap}/index.html?t=${Date.now()}`; // Force reload
      })
      .catch((error) => handleApiError(error, 'update map'))
      .finally(() => {
        reloadButton.disabled = false;
        reloadButton.textContent = 'Update Map';
      });
  });
}

/**
 * Sets up the toggle functionality for the marker input panel.
 */
function setupMarkerPanelToggle() {
  if (!markerButton || !markerForm) return;

  markerButton.addEventListener('click', () => {
    markerForm.classList.toggle('visible');
    markerButton.classList.toggle('active', markerForm.classList.contains('visible'));
  });
}

/**
 * Sets up the event listener for the "Add Marker" button.
 * Performs validation, requires password, and handles API interaction.
 */
function setupAddMarkerButton() {
  if (!addMarkerButton || !markerXInput || !markerZInput || !markerTextInput) {
    console.warn("One or more elements required for 'Add Marker' functionality are missing.");
    return;
  }

  addMarkerButton.addEventListener('click', () => {
    const xVal = markerXInput.value;
    const zVal = markerZInput.value;
    const textVal = markerTextInput.value.trim();
    const activeMap = document.querySelector('.map-button.active')?.getAttribute('data-map') || 'world';

    if (!xVal || !zVal || !textVal) {
      alert('Please provide X, Z coordinates and marker text.');
      return;
    }
    const x = parseInt(xVal, 10);
    const z = parseInt(zVal, 10);
    if (isNaN(x) || isNaN(z)) {
      alert('Coordinates (X, Z) must be numbers.');
      return;
    }
    if (textVal.length > 32) {
      alert('Marker text must be 32 characters or less.');
      return;
    }
    const markerData = { x, z, text: textVal };

    const userSecret = prompt('Password to add marker:');
    if (userSecret === null) return; // Cancelled
    if (!userSecret) {
      alert('Password cannot be empty.');
      return;
    }

    addMarkerButton.disabled = true;
    addMarkerButton.textContent = 'Adding...';

    fetch('/add_marker', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Action-Secret': userSecret },
      body: JSON.stringify({ map: activeMap, marker: markerData }),
    })
      .then((response) => {
        if (response.status === 401) throw new Error('Incorrect password.');
        if (!response.ok) {
          return response
            .json()
            .then((err) => Promise.reject(new Error(err.error || `HTTP ${response.status}`)))
            .catch(() => Promise.reject(new Error(`HTTP ${response.status}`)));
        }
        return response.json();
      })
      .then((data) => {
        alert(data.message || 'Marker added successfully.');
        markerXInput.value = '';
        markerZInput.value = '';
        markerTextInput.value = '';
        if (markerForm.classList.contains('visible')) {
          markerButton.click();
        }
        if (mapFrame) mapFrame.src = `/maps/${activeMap}/index.html?t=${Date.now()}`; // Force reload
      })
      .catch((error) => handleApiError(error, 'add marker'))
      .finally(() => {
        addMarkerButton.disabled = false;
        addMarkerButton.textContent = 'Add Marker';
      });
  });
}
