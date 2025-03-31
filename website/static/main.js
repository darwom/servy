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

// --- Koordinate aus Iframe holen ---
if (mapFrame) {
  window.addEventListener('keydown', (event) => {
    if (document.activeElement !== mapFrame && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) {
      if (event.ctrlKey && (event.key === 'c' || event.key === 'C')) {
        event.preventDefault();
        try {
          // Sende Anfrage an Iframe - Verwende sicheren Origin statt '*'
          const targetOrigin = mapFrame.contentWindow.location.origin; // oder '/' wenn immer same-origin
          mapFrame.contentWindow.postMessage({ type: 'requestCoordinates' }, targetOrigin);
        } catch (e) {
          console.error('Error sending message to iframe:', e);
        }
      }
    }
  });
}
window.addEventListener('message', (event) => {
  // Wichtig: Prüfe den Ursprung der Nachricht zur Sicherheit
  if (mapFrame && event.source === mapFrame.contentWindow && event.origin === window.location.origin) {
    const messageData = event.data;
    if (messageData && messageData.type === 'coordinates') {
      if (markerXInput) markerXInput.value = messageData.coords.x ?? '';
      if (markerZInput) markerZInput.value = messageData.coords.z ?? '';
    }
  }
});

// --- Spieleranzahl aktualisieren ---
const updatePlayerCount = () => {
  if (!playerCountElement) return;

  fetch('/get_player_count')
    .then((response) => (response.ok ? response.json() : Promise.reject('Network error')))
    .then((data) => {
      if (data.error) {
        playerCountElement.textContent = 'Server offline';
        playerCountElement.style.color = '#FF8080';
      } else if (data.online !== undefined) {
        const count = data.online;
        // Zeige "X Player online" (oder "1 Player" wenn nur einer)
        playerCountElement.textContent = `${count} Player${count !== 1 ? 's' : ''} online`;
        playerCountElement.style.color = '#FFF'; // Farbe zurücksetzen
      } else {
        // Sollte nicht passieren, aber sicher ist sicher
        playerCountElement.textContent = 'Error';
        playerCountElement.style.color = '#FF8080';
      }
    })
    .catch((error) => {
      console.error('Error fetching player count:', error);
      playerCountElement.textContent = 'Server offline';
      playerCountElement.style.color = '#FF8080';
    });
};

updatePlayerCount();
//setInterval(updatePlayerCount, 30000); // 30 Sekunden Intervall

// --- Hilfsfunktion für API Fehler ---
function handleApiError(error, action) {
  console.error(`${action} error:`, error);
  // Zeige spezifische Meldung für 401, sonst generisch
  const message = error.message && error.message.includes('password') ? 'Incorrect password.' : `Failed to ${action}. Please try again later.`;
  alert(message);
}

// --- Zeitstempel aktualisieren ---
const updateTimestamp = (map) => {
  fetch(`/get_file_date?map=${map}`)
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
    .then((data) => {
      timestampElement.textContent = data.last_updated ? `Map updated: ${data.last_updated}` : `Map updated: Error`;
    })
    .catch((err) => {
      console.error('Timestamp fetch error:', err);
      timestampElement.textContent = `Map updated: Network error`;
    });
};

// --- Map-Buttons ---
buttons.forEach((button) => {
  button.addEventListener('click', () => {
    buttons.forEach((btn) => btn.classList.remove('active'));
    button.classList.add('active');
    const map = button.getAttribute('data-map');
    if (mapFrame) mapFrame.src = `/maps/${map}/index.html`; // Nur Pfad ändern
    updateTimestamp(map);
  });
});

// --- Karte aktualisieren ---
if (reloadButton) {
  reloadButton.addEventListener('click', () => {
    const activeMap = document.querySelector('.map-button.active')?.getAttribute('data-map') || 'world';
    const userSecret = prompt('Please enter the password to update the map:');
    if (!userSecret) {
      alert('Map update cancelled.');
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
        if (response.status === 401) throw new Error('Incorrect password provided.');
        if (!response.ok)
          return response
            .json()
            .then((err) => Promise.reject(new Error(err.error || `HTTP ${response.status}`)))
            .catch(() => Promise.reject(new Error(`HTTP ${response.status}`)));
        return response.json();
      })
      .then((data) => {
        alert(data.message || 'Map update started successfully.');
        updateTimestamp(activeMap);
        if (mapFrame) mapFrame.src = `/maps/${activeMap}/index.html?t=${Date.now()}`; // Neu laden
      })
      .catch((error) => handleApiError(error, 'update map'))
      .finally(() => {
        reloadButton.disabled = false;
        reloadButton.textContent = 'Update Map';
      });
  });
}

// --- Marker Panel ---
if (markerButton && markerForm) {
  markerButton.addEventListener('click', () => {
    markerForm.classList.toggle('visible');
    markerButton.classList.toggle('active');
  });
}

// --- Marker hinzufügen ---
if (addMarkerButton) {
  addMarkerButton.addEventListener('click', () => {
    const x = markerXInput.value;
    const z = markerZInput.value;
    const text = markerTextInput.value.trim(); // Leerzeichen entfernen
    const activeMap = document.querySelector('.map-button.active')?.getAttribute('data-map') || 'world';

    if (!x || !z || !text) {
      alert('Please fill all marker fields.');
      return;
    }
    const markerData = { x: parseInt(x, 10), z: parseInt(z, 10), text: text };
    if (isNaN(markerData.x) || isNaN(markerData.z)) {
      alert('Coordinates must be numbers.');
      return;
    }
    if (text.length > 32) {
      alert('Marker text cannot exceed 32 characters.');
      return;
    }

    const userSecret = prompt('Please enter the password to add a marker:');
    if (!userSecret) {
      alert('Add marker cancelled.');
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
        if (response.status === 401) throw new Error('Incorrect password provided.');
        if (!response.ok)
          return response
            .json()
            .then((err) => Promise.reject(new Error(err.error || `HTTP ${response.status}`)))
            .catch(() => Promise.reject(new Error(`HTTP ${response.status}`)));
        return response.json();
      })
      .then((data) => {
        alert(data.message || 'Marker added successfully.');
        markerXInput.value = '';
        markerZInput.value = '';
        markerTextInput.value = '';
        if (mapFrame) mapFrame.src = `/maps/${activeMap}/index.html?t=${Date.now()}`; // Neu laden
      })
      .catch((error) => handleApiError(error, 'add marker'))
      .finally(() => {
        addMarkerButton.disabled = false;
        addMarkerButton.textContent = 'Add Marker';
      });
  });
}

// --- Initialer Ladevorgang ---
updateTimestamp('world');
window.addEventListener('load', () => {
  document.body.classList.remove('content-hidden');
  document.body.classList.add('content-visible');
});
