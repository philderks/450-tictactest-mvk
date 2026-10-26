package ch.bbw.m450.tictactoe;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;

/** Readable nine-cell boards for tests: X, O and . (empty). */
public final class BoardFixtures {
	private BoardFixtures() {
	}

	public static Stone[] toBoard(String cells) {
		if (cells.length() != TicTacToeMain.BOARD_SIZE) {
			throw new IllegalArgumentException("A board needs exactly nine cells");
		}
		var board = new Stone[TicTacToeMain.BOARD_SIZE];
		for (var i = 0; i < board.length; i++) {
			board[i] = switch (cells.charAt(i)) {
				case 'X' -> Stone.CROSS;
				case 'O' -> Stone.CIRCLE;
				case '.' -> null;
				default -> throw new IllegalArgumentException("Invalid board symbol: " + cells.charAt(i));
			};
		}
		return board;
	}
}
