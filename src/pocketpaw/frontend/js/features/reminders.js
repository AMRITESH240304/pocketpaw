/**
 * PocketPaw - Reminders Feature Module
 *
 * Created: 2026-02-05
 * Extracted from app.js as part of componentization refactor.
 *
 * Contains reminder-related state and methods:
 * - Reminder CRUD operations
 * - Reminder panel management
 * - Time formatting
 */

window.PocketPaw = window.PocketPaw || {};

window.PocketPaw.Reminders = {
    name: 'Reminders',
    /**
     * Get initial state for Reminders
     */
    getState() {
        return {
            showReminders: false,
            reminders: [],
            reminderInput: '',
            reminderLoading: false,
            reminderIntervalId: null,
            countdownTick: 0
        };
    },

    /**
     * Get methods for Reminders
     */
    getMethods() {
        return {
            /**
             * Handle reminders list
             */
            handleReminders(data) {
                this.reminders = data.reminders || [];
                this.reminderLoading = false;
            },

            /**
             * Handle reminder added
             */
            handleReminderAdded(data) {
                this.reminders.push(data.reminder);
                this.reminderInput = '';
                this.reminderLoading = false;
                this.showToast('Reminder set!', 'success');
            },

            /**
             * Handle reminder deleted
             */
            handleReminderDeleted(data) {
                this.reminders = this.reminders.filter(r => r.id !== data.id);
            },

            /**
             * Handle reminder triggered (notification)
             */
            handleReminderTriggered(data) {
                const reminder = data.reminder;
                this.showToast(`Reminder: ${reminder.text}`, 'info');
                this.addMessage('assistant', `Reminder: ${reminder.text}`);

                // Remove from local list
                this.reminders = this.reminders.filter(r => r.id !== reminder.id);

                // Try desktop notification
                if (Notification.permission === 'granted') {
                    new Notification('PocketPaw Reminder', {
                        body: reminder.text,
                        icon: '/static/icon.png'
                    });
                }
            },

            /**
             * Open reminders panel
             */
            openReminders() {
                this.showReminders = true;
                this.reminderLoading = true;
                socket.send('get_reminders');

                // Request notification permission
                if (Notification.permission === 'default') {
                    Notification.requestPermission();
                }

                // Start live countdown updates
                this.startReminderCountdown();

                this.$nextTick(() => {
                    if (window.refreshIcons) window.refreshIcons();
                });
            },

            /**
             * Start live countdown timer
             */
            startReminderCountdown() {
                if (this.reminderIntervalId) {
                    clearInterval(this.reminderIntervalId);
                }

                // Update countdown every second
                this.reminderIntervalId = setInterval(() => {
                    if (!this.showReminders) {
                        clearInterval(this.reminderIntervalId);
                        this.reminderIntervalId = null;
                        return;
                    }

                    this.countdownTick++;
                }, 1000);
            },

            /**
             * Calculate time remaining for a reminder (live countdown)
             */
            calculateTimeRemaining(reminder) {
                this.countdownTick;

                const now = new Date();
                const triggerTime = new Date(reminder.trigger_at);
                const diff = triggerTime - now;

                if (diff <= 0) {
                    return 'now';
                }

                const seconds = Math.floor(diff / 1000);
                const minutes = Math.floor(seconds / 60);
                const hours = Math.floor(minutes / 60);
                const days = Math.floor(hours / 24);

                if (days > 0) {
                    return `in ${days}d ${hours % 24}h ${minutes % 60}m ${seconds % 60}s`;
                } else if (hours > 0) {
                    return `in ${hours}h ${minutes % 60}m ${seconds % 60}s`;
                } else if (minutes > 0) {
                    return `in ${minutes}m ${seconds % 60}s`;
                } else {
                    return `in ${seconds}s`;
                }
            },

            /**
             * Add a reminder
             */
            addReminder() {
                const text = this.reminderInput.trim();
                if (!text) return;

                this.reminderLoading = true;
                socket.send('add_reminder', { message: text });
                this.log(`Setting reminder: ${text}`, 'info');
            },

            /**
             * Delete a reminder
             */
            deleteReminder(id) {
                socket.send('delete_reminder', { id });
            },

            /**
             * Format reminder time for display
             */
            formatReminderTime(reminder) {
                const date = new Date(reminder.trigger_at);
                return date.toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            }
        };
    }
};

window.PocketPaw.Loader.register('Reminders', window.PocketPaw.Reminders);
