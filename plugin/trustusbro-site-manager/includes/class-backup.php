<?php
/**
 * Backups and recovery.
 *
 * Backups are JSON snapshots of Site Manager content (documents, revisions
 * metadata, settings and design tokens) written to
 * wp-content/uploads/trustusbro-backups/. Nothing outside that folder is
 * modified when a backup is created, and restoring a backup never deletes posts:
 * it writes new revisions and repoints the published pointers.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Backup manager.
 */
class TUSB_Backup {

	/**
	 * Option holding the backup index.
	 */
	const INDEX_OPTION = 'tusb_backups';

	/**
	 * Maximum number of retained backups.
	 */
	const MAX_BACKUPS = 30;

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'admin_init', array( $this, 'maybe_schedule' ) );
		add_action( 'tusb_daily_backup', array( $this, 'scheduled_backup' ) );
	}

	/**
	 * Schedule a daily backup the first time the plugin runs.
	 *
	 * @return void
	 */
	public function maybe_schedule() {
		if ( ! wp_next_scheduled( 'tusb_daily_backup' ) ) {
			wp_schedule_event( time() + HOUR_IN_SECONDS, 'daily', 'tusb_daily_backup' );
		}
	}

	/**
	 * Scheduled backup callback.
	 *
	 * @return void
	 */
	public function scheduled_backup() {
		$this->create( 'scheduled' );
		$this->prune();
	}

	/**
	 * Directory for backups.
	 *
	 * @return string
	 */
	public function directory() {
		$uploads = wp_upload_dir( null, false );
		$dir     = trailingslashit( $uploads['basedir'] ) . 'trustusbro-backups';
		if ( ! is_dir( $dir ) ) {
			wp_mkdir_p( $dir );
		}
		// Never allow directory listing.
		if ( is_dir( $dir ) && ! file_exists( $dir . '/index.php' ) ) {
			@file_put_contents( $dir . '/index.php', "<?php\n// Silence is golden.\n" ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
			@file_put_contents( $dir . '/.htaccess', "Options -Indexes\n<FilesMatch \"\\.(json)$\">\nRequire all denied\n</FilesMatch>\n" ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
		}
		return $dir;
	}

	/**
	 * Create a backup.
	 *
	 * @param string $reason Reason label.
	 * @return array|WP_Error
	 */
	public function create( $reason = 'manual' ) {
		$store = tusb()->module( 'store' );
		if ( ! $store ) {
			return new WP_Error( 'tusb_no_store', __( 'The content store is unavailable.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		$dir  = $this->directory();
		$id   = gmdate( 'Ymd-His' ) . '-' . wp_generate_password( 4, false, false );
		$file = trailingslashit( $dir ) . 'tusb-backup-' . $id . '.json';

		$payload = array(
			'format'      => 'tusb-backup',
			'schema'      => 1,
			'plugin'      => TUSB_VERSION,
			'created'     => time(),
			'created_iso' => gmdate( 'c' ),
			'reason'      => sanitize_key( $reason ),
			'site'        => array(
				'url'     => home_url( '/' ),
				'name'    => get_bloginfo( 'name' ),
				'wp'      => get_bloginfo( 'version' ),
				'php'     => PHP_VERSION,
				'theme'   => wp_get_theme()->get_stylesheet(),
			),
			'user'        => get_current_user_id(),
			'settings'    => TUSB_Settings::all(),
			'documents'   => $store->export_all(),
		);

		$json = wp_json_encode( $payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
		if ( ! $json ) {
			return new WP_Error( 'tusb_backup_encode', __( 'The backup could not be encoded.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		$ok = @file_put_contents( $file, $json, LOCK_EX ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged, WordPress.WP.AlternativeFunctions
		if ( false === $ok ) {
			return new WP_Error( 'tusb_backup_write', __( 'The backup file could not be written. Check that wp-content/uploads is writable.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		$entry = array(
			'id'      => $id,
			'file'    => basename( $file ),
			'created' => time(),
			'reason'  => sanitize_key( $reason ),
			'size'    => strlen( $json ),
			'docs'    => count( $payload['documents'] ),
			'user'    => get_current_user_id(),
			'checksum'=> md5( $json ),
		);

		$index   = $this->index();
		$index[] = $entry;
		usort( $index, static function ( $a, $b ) {
			return $b['created'] <=> $a['created'];
		} );
		update_option( self::INDEX_OPTION, $index, false );

		update_option( 'tusb_last_backup', $entry, false );

		return $entry;
	}

	/**
	 * Backup index.
	 *
	 * @return array
	 */
	public function index() {
		$index = get_option( self::INDEX_OPTION, array() );
		if ( ! is_array( $index ) ) {
			return array();
		}
		// Drop entries whose files are gone (e.g. restored from another server).
		$dir = $this->directory();
		return array_values(
			array_filter(
				$index,
				static function ( $entry ) use ( $dir ) {
					if ( empty( $entry['file'] ) ) {
						return false;
					}
					return file_exists( trailingslashit( $dir ) . $entry['file'] );
				}
			)
		);
	}

	/**
	 * Path for a backup entry, validated against directory traversal.
	 *
	 * @param string $id Backup ID.
	 * @return string|WP_Error
	 */
	public function path_for( $id ) {
		$id = sanitize_file_name( (string) $id );
		foreach ( $this->index() as $entry ) {
			if ( $entry['id'] === $id ) {
				$path = trailingslashit( $this->directory() ) . $entry['file'];
				if ( realpath( $path ) && 0 === strpos( realpath( $path ), realpath( $this->directory() ) ) ) {
					return $path;
				}
			}
		}
		return new WP_Error( 'tusb_backup_missing', __( 'That backup could not be found.', 'trustusbro-site-manager' ), array( 'status' => 404 ) );
	}

	/**
	 * Read a backup's payload.
	 *
	 * @param string $id Backup ID.
	 * @return array|WP_Error
	 */
	public function read( $id ) {
		$path = $this->path_for( $id );
		if ( is_wp_error( $path ) ) {
			return $path;
		}
		$raw = @file_get_contents( $path ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged, WordPress.WP.AlternativeFunctions
		if ( false === $raw ) {
			return new WP_Error( 'tusb_backup_read', __( 'The backup file could not be read.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}
		$data = json_decode( $raw, true );
		if ( ! is_array( $data ) || ! isset( $data['documents'] ) ) {
			return new WP_Error( 'tusb_backup_invalid', __( 'That file is not a valid Site Manager backup.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}
		return $data;
	}

	/**
	 * Restore a backup: takes a safety snapshot first, then imports documents.
	 *
	 * @param string $id Backup ID.
	 * @return array|WP_Error
	 */
	public function restore( $id ) {
		$data = $this->read( $id );
		if ( is_wp_error( $data ) ) {
			return $data;
		}

		// Always snapshot immediately before restoring.
		$safety = $this->create( 'before-restore' );
		if ( is_wp_error( $safety ) ) {
			return new WP_Error(
				'tusb_restore_no_safety',
				__( 'Restore cancelled: a safety backup could not be created first. Check your uploads folder permissions.', 'trustusbro-site-manager' ),
				array( 'status' => 500 )
			);
		}

		$store = tusb()->module( 'store' );
		if ( ! $store ) {
			return new WP_Error( 'tusb_no_store', __( 'The content store is unavailable.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}

		$summary = $store->import_all( isset( $data['documents'] ) ? $data['documents'] : array() );

		if ( ! empty( $data['settings'] ) && is_array( $data['settings'] ) ) {
			update_option( TUSB_Settings::OPTION, $data['settings'], false );
		}

		return array(
			'ok'       => true,
			'summary'  => $summary,
			'safety'   => $safety,
			'imported' => count( $summary['imported'] ),
			'failed'   => count( $summary['failed'] ),
		);
	}

	/**
	 * Import a backup from an uploaded JSON file.
	 *
	 * @param array $file $_FILES entry.
	 * @return array|WP_Error
	 */
	public function import_file( $file ) {
		if ( empty( $file['tmp_name'] ) || ! is_uploaded_file( $file['tmp_name'] ) ) {
			return new WP_Error( 'tusb_upload', __( 'The file could not be uploaded.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}
		if ( ! empty( $file['size'] ) && $file['size'] > 16 * MB_IN_BYTES ) {
			return new WP_Error( 'tusb_upload_size', __( 'That file is too large (maximum 16 MB).', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$raw = @file_get_contents( $file['tmp_name'] ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged, WordPress.WP.AlternativeFunctions
		$data = json_decode( (string) $raw, true );
		if ( ! is_array( $data ) || ! isset( $data['documents'] ) ) {
			return new WP_Error( 'tusb_upload_invalid', __( 'That file is not a valid Site Manager backup.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$safety = $this->create( 'before-import' );
		if ( is_wp_error( $safety ) ) {
			return $safety;
		}

		$store = tusb()->module( 'store' );
		if ( ! $store ) {
			return new WP_Error( 'tusb_no_store', __( 'The content store is unavailable.', 'trustusbro-site-manager' ), array( 'status' => 500 ) );
		}
		$summary = $store->import_all( $data['documents'] );

		return array(
			'ok'      => true,
			'summary' => $summary,
			'safety'  => $safety,
		);
	}

	/**
	 * Delete a backup file and its index entry.
	 *
	 * @param string $id Backup ID.
	 * @return array|WP_Error
	 */
	public function delete( $id ) {
		$path = $this->path_for( $id );
		if ( is_wp_error( $path ) ) {
			return $path;
		}
		@unlink( $path ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
		$index = array_values(
			array_filter(
				$this->index(),
				static function ( $entry ) use ( $id ) {
					return $entry['id'] !== $id;
				}
			)
		);
		update_option( self::INDEX_OPTION, $index, false );
		return array( 'ok' => true, 'deleted' => $id );
	}

	/**
	 * Keep only the newest MAX_BACKUPS entries.
	 *
	 * @return void
	 */
	public function prune() {
		$index = $this->index();
		if ( count( $index ) <= self::MAX_BACKUPS ) {
			return;
		}
		$keep    = array_slice( $index, 0, self::MAX_BACKUPS );
		$removed = array_slice( $index, self::MAX_BACKUPS );
		foreach ( $removed as $entry ) {
			@unlink( trailingslashit( $this->directory() ) . $entry['file'] ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
		}
		update_option( self::INDEX_OPTION, $keep, false );
	}

	/**
	 * Export the current state as a downloadable JSON string.
	 *
	 * @return string
	 */
	public function export_string() {
		$store = tusb()->module( 'store' );
		$payload = array(
			'format'    => 'tusb-backup',
			'schema'    => 1,
			'plugin'    => TUSB_VERSION,
			'created'   => time(),
			'reason'    => 'download',
			'site'      => array( 'url' => home_url( '/' ), 'name' => get_bloginfo( 'name' ) ),
			'settings'  => TUSB_Settings::all(),
			'documents' => $store ? $store->export_all() : array(),
		);
		return (string) wp_json_encode( $payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
	}
}
