/**
 * Utility functions for signing sensitive actions with WebAuthn/Passkeys
 */

function b64urlToBuffer(base64url) {
    const padding = '='.repeat((4 - (base64url.length % 4)) % 4);
    const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    const buffer = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) {
        buffer[i] = raw.charCodeAt(i);
    }
    return buffer.buffer;
}

function bufferToB64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i += 1) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function normalizeAuthOptions(publicKey) {
    const options = { ...publicKey };
    options.challenge = b64urlToBuffer(options.challenge);
    if (Array.isArray(options.allowCredentials)) {
        options.allowCredentials = options.allowCredentials.map((item) => ({
            ...item,
            id: b64urlToBuffer(item.id),
        }));
    }
    return options;
}

function normalizeAssertion(credential) {
    return {
        id: credential.id,
        rawId: bufferToB64url(credential.rawId),
        type: credential.type,
        response: {
            authenticatorData: bufferToB64url(credential.response.authenticatorData),
            clientDataJSON: bufferToB64url(credential.response.clientDataJSON),
            signature: bufferToB64url(credential.response.signature),
            userHandle: credential.response.userHandle ? bufferToB64url(credential.response.userHandle) : null,
        },
    };
}

/**
 * Sign a sensitive action using the user's passkey.
 * Shows minimal UI - just status updates in provided element.
 * 
 * @param {string} actionLabel - Human-readable description of the action (e.g., "limpieza de bitácora")
 * @param {HTMLElement} statusNode - Element to display status messages
 * @param {string} csrfToken - CSRF token from the page
 * @param {function} onSuccess - Callback when signature is successful
 * @returns {Promise<boolean>} True if signature successful, false otherwise
 */
async function signActionWithPasskey(actionLabel, statusNode, csrfToken, onSuccess) {
    if (!window.PublicKeyCredential) {
        statusNode.textContent = 'Este navegador no soporta passkeys.';
        statusNode.style.color = '#c53030';
        return false;
    }

    statusNode.textContent = 'Solicitando desafío de firma...';
    statusNode.style.color = '#4b5563';

    try {
        // Step 1: Get challenge options
        const optionsResp = await fetch('/action/passkey/options', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken,
            },
            body: JSON.stringify({}),
        });
        
        const optionsData = await optionsResp.json();
        if (!optionsResp.ok || !optionsData.ok) {
            statusNode.textContent = optionsData.message || 'No se pudo generar el desafío.';
            statusNode.style.color = '#c53030';
            return false;
        }

        // Step 2: Ask user to sign with passkey
        statusNode.textContent = 'Abre tu password manager o autenticador...';
        statusNode.style.color = '#4b5563';
        
        let assertion;
        try {
            assertion = await navigator.credentials.get({
                publicKey: normalizeAuthOptions(optionsData.publicKey),
            });
        } catch (err) {
            statusNode.textContent = 'Firma cancelada o error: ' + (err.message || err);
            statusNode.style.color = '#c53030';
            return false;
        }

        if (!assertion) {
            statusNode.textContent = 'Firma cancelada por el usuario.';
            statusNode.style.color = '#c53030';
            return false;
        }

        // Step 3: Verify signature on server
        statusNode.textContent = 'Verificando firma...';
        statusNode.style.color = '#4b5563';

        const verifyResp = await fetch('/action/passkey/verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken,
            },
            body: JSON.stringify({
                credential: normalizeAssertion(assertion),
                action_label: actionLabel,
            }),
        });

        const verifyData = await verifyResp.json();
        if (!verifyResp.ok || !verifyData.ok) {
            statusNode.textContent = verifyData.message || 'No se pudo verificar la firma.';
            statusNode.style.color = '#c53030';
            return false;
        }

        statusNode.textContent = '✓ Firma verificada correctamente';
        statusNode.style.color = '#27ae60';
        
        // Call success callback if provided
        if (onSuccess && typeof onSuccess === 'function') {
            onSuccess();
        }
        
        return true;
    } catch (err) {
        statusNode.textContent = 'Error de conexión: ' + (err.message || err);
        statusNode.style.color = '#c53030';
        return false;
    }
}
