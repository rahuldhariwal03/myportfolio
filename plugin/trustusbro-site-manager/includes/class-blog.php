<?php
/**
 * Blog management.
 *
 * Uses native WordPress posts and categories. Nothing is duplicated and no new
 * content types are introduced for articles, so existing URLs, feeds, sitemaps
 * and SEO plugins keep working.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Blog.
 */
class TUSB_Blog {

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_filter( 'the_content', array( $this, 'append_related_posts' ), 30 );
		add_action( 'wp_head', array( $this, 'blog_meta' ), 3 );
		add_filter( 'get_the_excerpt', array( $this, 'fallback_excerpt' ), 10, 2 );
	}

	/**
	 * Add related posts after single post content.
	 *
	 * @param string $content Content.
	 * @return string
	 */
	public function append_related_posts( $content ) {
		if ( ! is_singular( 'post' ) || ! in_the_loop() || ! is_main_query() ) {
			return $content;
		}
		$related = $this->related_posts( get_the_ID(), 3 );
		if ( ! $related ) {
			return $content;
		}

		$html  = '<aside class="tusb-related" aria-labelledby="tusb-related-title">';
		$html .= '<h2 class="tusb-related__title" id="tusb-related-title">' . esc_html__( 'Related articles', 'trustusbro-site-manager' ) . '</h2>';
		$html .= '<ul class="tusb-related__list">';
		foreach ( $related as $post ) {
			$html .= '<li class="tusb-related__item">';
			if ( has_post_thumbnail( $post ) ) {
				$html .= '<a class="tusb-related__thumb" href="' . esc_url( get_permalink( $post ) ) . '" tabindex="-1" aria-hidden="true">' . get_the_post_thumbnail( $post, 'medium', array( 'loading' => 'lazy', 'alt' => '' ) ) . '</a>';
			}
			$html .= '<div class="tusb-related__body">';
			$html .= '<a class="tusb-related__link" href="' . esc_url( get_permalink( $post ) ) . '">' . esc_html( get_the_title( $post ) ) . '</a>';
			$html .= '<time class="tusb-related__date" datetime="' . esc_attr( get_the_date( 'c', $post ) ) . '">' . esc_html( get_the_date( '', $post ) ) . '</time>';
			$html .= '</div></li>';
		}
		$html .= '</ul></aside>';

		return $content . $html;
	}

	/**
	 * Related posts: same category first, then most recent.
	 *
	 * @param int $post_id Post ID.
	 * @param int $limit Limit.
	 * @return WP_Post[]
	 */
	public function related_posts( $post_id, $limit = 3 ) {
		$post_id = (int) $post_id;
		$args    = array(
			'post_type'           => 'post',
			'post_status'         => 'publish',
			'posts_per_page'      => (int) $limit,
			'post__not_in'        => array( $post_id ),
			'ignore_sticky_posts' => true,
			'no_found_rows'       => true,
		);

		$categories = wp_get_post_categories( $post_id );
		if ( $categories ) {
			$args['category__in'] = $categories;
		}

		$related = get_posts( $args );
		if ( count( $related ) >= $limit ) {
			return $related;
		}

		unset( $args['category__in'] );
		$exclude = array_merge( array( $post_id ), wp_list_pluck( $related, 'ID' ) );
		$args['post__not_in'] = $exclude;
		$args['posts_per_page'] = (int) $limit - count( $related );

		return array_merge( $related, get_posts( $args ) );
	}

	/**
	 * Add article meta that themes commonly omit.
	 *
	 * @return void
	 */
	public function blog_meta() {
		if ( ! is_singular( 'post' ) ) {
			return;
		}
		$post_id = get_queried_object_id();
		$author  = get_the_author_meta( 'display_name', (int) get_post_field( 'post_author', $post_id ) );
		printf(
			'<meta name="author" content="%s" />' . "\n",
			esc_attr( $author )
		);
	}

	/**
	 * Use the excerpt, then the content, then the SEO description as an excerpt.
	 *
	 * @param string  $excerpt Excerpt.
	 * @param WP_Post $post Post.
	 * @return string
	 */
	public function fallback_excerpt( $excerpt, $post = null ) {
		if ( '' !== trim( (string) $excerpt ) ) {
			return $excerpt;
		}
		if ( ! $post instanceof WP_Post ) {
			return $excerpt;
		}
		$content = wp_strip_all_tags( strip_shortcodes( (string) $post->post_content ) );
		if ( '' === trim( $content ) ) {
			$seo = get_post_meta( $post->ID, '_tusb_seo_description', true );
			$content = $seo ? $seo : '';
		}
		return wp_trim_words( $content, 28, '…' );
	}

	/**
	 * Data for the Blog Manager screen.
	 *
	 * @param array $args Filters: status, category, search, page.
	 * @return array
	 */
	public function listing( $args = array() ) {
		$per_page = isset( $args['per_page'] ) ? max( 1, min( 100, (int) $args['per_page'] ) ) : 20;
		$page     = isset( $args['page'] ) ? max( 1, (int) $args['page'] ) : 1;

		$query_args = array(
			'post_type'      => 'post',
			'post_status'    => isset( $args['status'] ) && 'all' !== $args['status'] ? sanitize_key( $args['status'] ) : array( 'publish', 'draft', 'pending', 'future', 'private' ),
			'posts_per_page' => $per_page,
			'paged'          => $page,
			'orderby'        => 'date',
			'order'          => 'DESC',
		);

		if ( ! empty( $args['category'] ) ) {
			$query_args['category_name'] = sanitize_title( $args['category'] );
		}

		$query = new WP_Query( $query_args );

		$posts = array();
		foreach ( $query->posts as $post ) {
			$posts[] = $this->format_post( $post );
		}

		return array(
			'items'      => $posts,
			'total'      => (int) $query->found_posts,
			'pages'      => (int) $query->max_num_pages,
			'page'       => $page,
			'categories' => $this->categories(),
			'counts'     => wp_count_posts( 'post' ),
		);
	}

	/**
	 * Format one post for the dashboard.
	 *
	 * @param WP_Post $post Post.
	 * @return array
	 */
	public function format_post( $post ) {
		$categories = array();
		foreach ( (array) get_the_category( $post->ID ) as $category ) {
			$categories[] = array(
				'id'   => (int) $category->term_id,
				'name' => $category->name,
				'url'  => get_category_link( $category ),
			);
		}

		return array(
			'id'          => (int) $post->ID,
			'title'       => get_the_title( $post ),
			'slug'        => $post->post_name,
			'status'      => $post->post_status,
			'status_label'=> $this->status_label( $post->post_status ),
			'date'        => get_the_date( 'c', $post ),
			'date_label'  => get_the_date( '', $post ),
			'modified'    => get_the_modified_date( 'c', $post ),
			'author'      => get_the_author_meta( 'display_name', (int) $post->post_author ),
			'categories'  => $categories,
			'excerpt'     => $this->fallback_excerpt( '', $post ),
			'thumbnail'   => get_the_post_thumbnail_url( $post, 'medium' ) ?: '',
			'edit_link'   => get_edit_post_link( $post->ID, 'raw' ),
			'view_link'   => get_permalink( $post ),
			'seo_title'   => (string) get_post_meta( $post->ID, '_tusb_seo_title', true ),
			'seo_desc'    => (string) get_post_meta( $post->ID, '_tusb_seo_description', true ),
			'comment_count' => (int) $post->comment_count,
		);
	}

	/**
	 * Human status label.
	 *
	 * @param string $status Status.
	 * @return string
	 */
	public function status_label( $status ) {
		$labels = array(
			'publish' => __( 'Published', 'trustusbro-site-manager' ),
			'draft'   => __( 'Draft', 'trustusbro-site-manager' ),
			'pending' => __( 'Pending review', 'trustusbro-site-manager' ),
			'future'  => __( 'Scheduled', 'trustusbro-site-manager' ),
			'private' => __( 'Private', 'trustusbro-site-manager' ),
			'trash'   => __( 'Trashed', 'trustusbro-site-manager' ),
		);
		return isset( $labels[ $status ] ) ? $labels[ $status ] : ucfirst( $status );
	}

	/**
	 * Categories for the dashboard and the category editor.
	 *
	 * @return array
	 */
	public function categories() {
		$terms = get_terms(
			array(
				'taxonomy'   => 'category',
				'hide_empty' => false,
			)
		);
		$out = array();
		if ( is_wp_error( $terms ) ) {
			return $out;
		}
		foreach ( $terms as $term ) {
			$out[] = array(
				'id'          => (int) $term->term_id,
				'name'        => $term->name,
				'slug'        => $term->slug,
				'description' => $term->description,
				'count'       => (int) $term->count,
				'url'         => get_category_link( $term ),
			);
		}
		return $out;
	}

	/**
	 * Create or update a category.
	 *
	 * @param array $args name, slug, description, id.
	 * @return array|WP_Error
	 */
	public function save_category( $args ) {
		$name = isset( $args['name'] ) ? sanitize_text_field( $args['name'] ) : '';
		if ( '' === $name ) {
			return new WP_Error( 'tusb_cat_name', __( 'Please give the category a name.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$term_args = array(
			'description' => isset( $args['description'] ) ? sanitize_textarea_field( $args['description'] ) : '',
		);
		if ( ! empty( $args['slug'] ) ) {
			$term_args['slug'] = sanitize_title( $args['slug'] );
		}

		$result = ! empty( $args['id'] )
			? wp_update_term( (int) $args['id'], 'category', array_merge( array( 'name' => $name ), $term_args ) )
			: wp_insert_term( $name, 'category', $term_args );

		if ( is_wp_error( $result ) ) {
			return $result;
		}

		return array(
			'ok'   => true,
			'id'   => isset( $result['term_id'] ) ? (int) $result['term_id'] : 0,
			'data' => $this->categories(),
		);
	}

	/**
	 * Delete a category (posts are not deleted; they fall back to Uncategorised).
	 *
	 * @param int $term_id Term ID.
	 * @return array|WP_Error
	 */
	public function delete_category( $term_id ) {
		$term_id  = (int) $term_id;
		$default  = (int) get_option( 'default_category' );
		if ( $term_id === $default ) {
			return new WP_Error( 'tusb_cat_default', __( 'The default category cannot be deleted.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}
		$result = wp_delete_term( $term_id, 'category' );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return array( 'ok' => (bool) $result, 'data' => $this->categories() );
	}

	/**
	 * Create or update a post from the dashboard.
	 *
	 * @param array $args Post fields.
	 * @return array|WP_Error
	 */
	public function save_post( $args ) {
		$id    = isset( $args['id'] ) ? (int) $args['id'] : 0;
		$title = isset( $args['title'] ) ? sanitize_text_field( $args['title'] ) : '';

		if ( '' === $title ) {
			return new WP_Error( 'tusb_post_title', __( 'Please give the article a title.', 'trustusbro-site-manager' ), array( 'status' => 400 ) );
		}

		$postarr = array(
			'post_type'    => 'post',
			'post_title'   => $title,
			'post_content' => isset( $args['content'] ) ? wp_kses_post( $args['content'] ) : '',
			'post_excerpt' => isset( $args['excerpt'] ) ? sanitize_textarea_field( $args['excerpt'] ) : '',
		);

		$status = isset( $args['status'] ) ? sanitize_key( $args['status'] ) : 'draft';
		if ( ! in_array( $status, array( 'publish', 'draft', 'pending', 'future', 'private' ), true ) ) {
			$status = 'draft';
		}
		$postarr['post_status'] = $status;

		if ( ! empty( $args['date'] ) ) {
			$timestamp = strtotime( $args['date'] );
			if ( $timestamp ) {
				$postarr['post_date']     = wp_date( 'Y-m-d H:i:s', $timestamp );
				$postarr['post_date_gmt'] = gmdate( 'Y-m-d H:i:s', $timestamp );
			}
		}

		if ( $id ) {
			if ( ! current_user_can( 'edit_post', $id ) ) {
				return new WP_Error( 'tusb_forbidden', __( 'You are not allowed to edit that article.', 'trustusbro-site-manager' ), array( 'status' => 403 ) );
			}
			$postarr['ID'] = $id;
			$result        = wp_update_post( $postarr, true );
		} else {
			$result = wp_insert_post( $postarr, true );
		}

		if ( is_wp_error( $result ) ) {
			return $result;
		}

		$post_id = (int) $result;

		if ( isset( $args['categories'] ) ) {
			$cats = array_map( 'absint', (array) $args['categories'] );
			wp_set_post_categories( $post_id, $cats );
		}

		if ( isset( $args['tags'] ) ) {
			$tags = is_array( $args['tags'] ) ? $args['tags'] : array_filter( array_map( 'trim', explode( ',', (string) $args['tags'] ) ) );
			wp_set_post_tags( $post_id, array_map( 'sanitize_text_field', $tags ) );
		}

		if ( ! empty( $args['thumbnail'] ) ) {
			$thumb = TUSB_Sanitizer::image_id( $args['thumbnail'] );
			if ( $thumb ) {
				set_post_thumbnail( $post_id, $thumb );
			}
		} elseif ( array_key_exists( 'thumbnail', $args ) ) {
			delete_post_thumbnail( $post_id );
		}

		foreach ( array( 'seo_title' => '_tusb_seo_title', 'seo_desc' => '_tusb_seo_description', 'seo_canonical' => '_tusb_seo_canonical' ) as $field => $meta_key ) {
			if ( array_key_exists( $field, $args ) ) {
				update_post_meta( $post_id, $meta_key, sanitize_text_field( (string) $args[ $field ] ) );
			}
		}
		if ( array_key_exists( 'noindex', $args ) ) {
			update_post_meta( $post_id, '_tusb_seo_noindex', TUSB_Sanitizer::to_bool( $args['noindex'] ) ? 1 : 0 );
		}

		return array(
			'ok'   => true,
			'id'   => $post_id,
			'post' => $this->format_post( get_post( $post_id ) ),
		);
	}
}
