/**
 * Periwatch PDF Generator Client
 * Frontend JavaScript untuk menggunakan sistem PDF generation dengan timeout
 */

class PeriwatchPDFClient {
    constructor(baseUrl, authToken) {
        this.baseUrl = baseUrl.replace(/\/$/, ''); // Remove trailing slash
        this.authToken = authToken;
        this.headers = {
            'Authorization': `Bearer ${authToken}`
        };
    }

    /**
     * Generate PDF dengan timeout dan background processing
     * @param {Object} options - PDF generation options
     * @param {string} options.title - Title report
     * @param {string} options.email - Email untuk notifikasi
     * @param {string} options.ticker - Ticker symbol (optional)
     * @param {string} options.company - Company name (optional)
     * @param {number} options.timeout - Timeout dalam detik (default: 30)
     * @param {Function} options.onProgress - Callback untuk update progress
     * @returns {Promise<Object>} Result object
     */
    async generatePDF(options) {
        const {
            title = 'Periwatch Report',
            email,
            ticker = '',
            company = '',
            timeout = 30,
            onProgress
        } = options;

        if (!email) {
            throw new Error('Email is required');
        }

        // Build query parameters
        const params = new URLSearchParams({
            title,
            email,
            timeout: timeout.toString()
        });

        if (ticker) params.append('ticker', ticker);
        if (company) params.append('company', company);

        try {
            if (onProgress) onProgress('Generating PDF...', 0);

            const response = await fetch(`${this.baseUrl}/api/generate-pdf/?${params}`, {
                method: 'GET',
                headers: this.headers,
                mode: 'cors',
                credentials: 'omit'
            });

            if (!response.ok && response.status !== 202) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            // Handle HTTP 202 (Accepted) - background processing without partial PDF
            if (response.status === 202) {
                const responseData = await response.json();
                if (onProgress) onProgress('Processing in background, will be emailed when ready', 25);
                
                // Start monitoring background task
                this.monitorTask(responseData.task_id, onProgress);
                
                return {
                    status: 'processing_background',
                    taskId: responseData.task_id,
                    message: responseData.message,
                    pdfBlob: null,
                    pdfUrl: null,
                    downloadFilename: null
                };
            }

            const pdfStatus = response.headers.get('X-PDF-Status');
            const taskId = response.headers.get('X-Task-ID');
            const message = response.headers.get('X-Message');
            const pdfBlob = await response.blob();

            const result = {
                status: pdfStatus,
                taskId,
                message,
                pdfBlob,
                pdfUrl: URL.createObjectURL(pdfBlob)
            };

            if (pdfStatus === 'completed') {
                if (onProgress) onProgress('PDF completed', 100);
                result.downloadFilename = `${title}.pdf`;
            } else if (pdfStatus === 'partial') {
                if (onProgress) onProgress('PDF partially generated, full version will be emailed', 50);
                result.downloadFilename = `${title}_partial.pdf`;
                
                // Start monitoring background task
                this.monitorTask(taskId, onProgress);
            }

            return result;

        } catch (error) {
            if (onProgress) onProgress(`Error: ${error.message}`, -1);
            throw error;
        }
    }

    /**
     * Monitor background task status
     * @param {string} taskId - Task ID to monitor
     * @param {Function} onProgress - Progress callback
     * @returns {Promise<Object>} Final task status
     */
    async monitorTask(taskId, onProgress) {
        const maxChecks = 30; // Maximum 30 checks (2.5 minutes)
        let checkCount = 0;

        const checkStatus = async () => {
            try {
                const response = await fetch(`${this.baseUrl}/api/task-status/${taskId}/`, {
                    headers: this.headers,
                    mode: 'cors',
                    credentials: 'omit'
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const statusData = await response.json();
                const { status } = statusData;

                if (onProgress) {
                    const progressMessage = this.getProgressMessage(status);
                    const progressPercent = this.getProgressPercent(status);
                    onProgress(progressMessage, progressPercent);
                }

                if (status === 'completed_and_sent') {
                    return statusData;
                } else if (status === 'failed') {
                    throw new Error(statusData.error || 'Task failed');
                } else if (checkCount < maxChecks) {
                    checkCount++;
                    setTimeout(checkStatus, 5000); // Check again in 5 seconds
                } else {
                    if (onProgress) onProgress('Monitoring timeout - check your email', 90);
                }

            } catch (error) {
                if (onProgress) onProgress(`Monitoring error: ${error.message}`, -1);
                throw error;
            }
        };

        return checkStatus();
    }

    /**
     * Get progress message for different task statuses
     */
    getProgressMessage(status) {
        const messages = {
            'running': 'Generating PDF...',
            'completed': 'PDF completed',
            'partial': 'PDF partially generated',
            'processing_background': 'Generating full PDF in background...',
            'completed_and_sent': 'PDF completed and sent to email',
            'failed': 'PDF generation failed'
        };
        return messages[status] || 'Processing...';
    }

    /**
     * Get progress percentage for different task statuses
     */
    getProgressPercent(status) {
        const percentages = {
            'running': 25,
            'completed': 100,
            'partial': 50,
            'processing_background': 75,
            'completed_and_sent': 100,
            'failed': -1
        };
        return percentages[status] || 0;
    }

    /**
     * Download PDF blob as file
     * @param {Blob} pdfBlob - PDF blob to download
     * @param {string} filename - Download filename
     */
    downloadPDF(pdfBlob, filename) {
        const url = URL.createObjectURL(pdfBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /**
     * Cleanup old tasks
     * @param {number} hours - Hours threshold for cleanup
     * @returns {Promise<string>} Cleanup message
     */
    async cleanupTasks(hours = 24) {
        try {
            const response = await fetch(`${this.baseUrl}/api/cleanup-tasks/`, {
                method: 'POST',
                headers: {
                    ...this.headers,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ hours }),
                mode: 'cors',
                credentials: 'omit'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            return result.message;

        } catch (error) {
            throw new Error(`Cleanup failed: ${error.message}`);
        }
    }
}

// Example usage
/*
const pdfClient = new PeriwatchPDFClient('http://localhost:8000', 'your_password');

// Generate PDF with progress tracking
pdfClient.generatePDF({
    title: 'My Company Report',
    email: 'user@example.com',
    company: 'Bank Central Asia',
    timeout: 30,
    onProgress: (message, percent) => {
        console.log(`${message} (${percent}%)`);
        if (percent >= 0) {
            updateProgressBar(percent);
        }
    }
}).then(result => {
    console.log('PDF Generation Result:', result);
    
    if (result.status === 'completed' || result.status === 'partial') {
        // Auto-download PDF
        pdfClient.downloadPDF(result.pdfBlob, result.downloadFilename);
    }
}).catch(error => {
    console.error('PDF Generation Error:', error);
});
*/

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PeriwatchPDFClient;
} else if (typeof window !== 'undefined') {
    window.PeriwatchPDFClient = PeriwatchPDFClient;
}
