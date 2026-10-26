package ch.bbw.m450.tictactoe;

import static ch.bbw.m450.tictactoe.BoardFixtures.toBoard;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import ch.bbw.m450.tictactoe.players.GreedyPlayer;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class TicTacToeMainTest {

	@Test
	void isWin_returnsNoWinnerForDrawBoard() {
		var board = toBoard("XOXXOOOXX");

		assertThat(Arrays.stream(Stone.values())
				.filter(color -> TicTacToeMain.isWin(board, color))
				.toList()).isEmpty();
	}

	@ParameterizedTest(name = "positions {0} won by {1}")
	@MethodSource("winningLines")
	void isWin_detectsAllWinningLines(int[] positions, Stone color) {
		var board = new Stone[TicTacToeMain.BOARD_SIZE];
		for (var position : positions) {
			board[position] = color;
		}

		assertThat(Arrays.stream(Stone.values())
				.filter(candidate -> TicTacToeMain.isWin(board, candidate))
				.toList()).as("winner for line %s", Arrays.toString(positions))
				.containsExactly(color);
	}

	private static Stream<Arguments> winningLines() {
		return Stream.of(
				// rows
				Arguments.of(new int[]{0, 1, 2}, Stone.CROSS),
				Arguments.of(new int[]{3, 4, 5}, Stone.CIRCLE),
				Arguments.of(new int[]{6, 7, 8}, Stone.CROSS),
				// columns
				Arguments.of(new int[]{0, 3, 6}, Stone.CIRCLE),
				Arguments.of(new int[]{1, 4, 7}, Stone.CROSS),
				Arguments.of(new int[]{2, 5, 8}, Stone.CIRCLE),
				// diagonals
				Arguments.of(new int[]{0, 4, 8}, Stone.CROSS),
				Arguments.of(new int[]{2, 4, 6}, Stone.CIRCLE)
		);
	}

	@Test
	void play_throwsIllegalArgumentException_whenSamePlayerInstanceUsedForBothSides() {
		var player = new GreedyPlayer();

		assertThatThrownBy(() -> TicTacToeMain.play(player, player))
				.isInstanceOf(IllegalArgumentException.class);
	}

	@Test
	void play_withTwoGreedyPlayers_producesDeterministicCrossWin() {
		// GreedyPlayer always fills the first free field: X takes 0,2,4,6 and
		// wins via the 2-4-6 anti-diagonal before O gets to move a 4th time.
		var winner = TicTacToeMain.play(new GreedyPlayer(), new GreedyPlayer());

		assertThat(winner).isEqualTo(Stone.CROSS);
	}

	@Test
	void play_throwsIllegalStateException_whenPlayerReturnsOutOfRangePosition() {
		var brokenPlayer = new QueuePlayer(-1);

		assertThatThrownBy(() -> TicTacToeMain.play(brokenPlayer, new GreedyPlayer()))
				.isInstanceOf(IllegalStateException.class);
	}

	@Test
	void play_returnsNull_onDraw() {
		// X: 0,2,3,7,8  O: 1,4,5,6 -> full board, no line for either color
		var xPlayer = new QueuePlayer(0, 2, 3, 7, 8);
		var oPlayer = new QueuePlayer(1, 4, 5, 6);

		var winner = TicTacToeMain.play(xPlayer, oPlayer);

		assertThat(winner).isNull();
	}

	/**
	 * Test double that plays a fixed, predetermined sequence of moves, ignoring the board.
	 */
	private static class QueuePlayer implements TicTacToePlayer {

		private final Deque<Integer> moves;

		QueuePlayer(int... moves) {
			this.moves = new ArrayDeque<>();
			for (var move : moves) {
				this.moves.add(move);
			}
		}

		@Override
		public int play(Stone[] board, Stone colorToPlay) {
			return moves.poll();
		}
	}
}
